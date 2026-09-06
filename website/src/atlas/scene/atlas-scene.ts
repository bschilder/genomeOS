/** Cesium lifecycle and scientific-layer orchestration for Atlas design §11. */

import {
  Color,
  Credit,
  GeoJsonDataSource,
  ImageryLayer,
  SceneMode,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Viewer,
  type GeoJsonDataSource as GeoJsonSource,
} from 'cesium';

import type { ObservationArtifact, SurfaceArtifact } from '../contracts';
import type { Metric } from '../visual-encoding';
import type {
  CameraState,
  ExplorerSceneMode,
  LayerVisibility,
} from '../url-state';
import { bindKeyboardCamera, cameraState, setCameraState } from './camera';
import {
  buildObservationLayer,
  type ObservationPick,
  type ObservationPrimitiveGroup,
} from './observation-layer';
import {
  buildSurfaceLayer,
  type ScientificPrimitiveGroup,
  type SurfacePick,
} from './surface-layer';

export type AtlasPick = SurfacePick | ObservationPick;
export type ContextStatus = 'loading' | 'ready' | 'fallback';

export interface AtlasSceneOptions {
  contextImageryUrl?: string;
  naturalEarthUrl: string;
  reducedMotion?: boolean;
}

export interface AtlasSceneController {
  setArtifact(
    surface: SurfaceArtifact,
    observations: ObservationArtifact,
  ): Promise<void>;
  setMetric(metric: Metric): Promise<void>;
  setLayerVisibility(layers: LayerVisibility): void;
  setElevation(enabled: boolean, exaggeration: number): Promise<void>;
  setSceneMode(mode: ExplorerSceneMode, reducedMotion: boolean): Promise<void>;
  setCamera(camera: CameraState, animated: boolean): void;
  home(animated: boolean): void;
  zoom(direction: 'in' | 'out'): void;
  onPick(listener: (pick: AtlasPick | null) => void): () => void;
  onCameraSettled(listener: (camera: CameraState) => void): () => void;
  onContextStatus(listener: (status: ContextStatus) => void): () => void;
  destroy(): void;
}

type FadeableGroup = ScientificPrimitiveGroup | ObservationPrimitiveGroup;

const DEFAULT_LAYERS: LayerVisibility = {
  context: true,
  observations: true,
  support: true,
  surface: true,
};
const HOME_CAMERA: CameraState = {
  heading: 0,
  height: 16_500_000,
  lat: 12,
  lon: 20,
  pitch: -90,
};
const HEATMAP_TRANSITION_MS = 720;

export function resolveElevationView(
  view: ExplorerSceneMode,
  elevationEnabled: boolean,
): ExplorerSceneMode {
  return view === 'map' && elevationEnabled ? 'perspective' : view;
}

export function transitionProgress(
  elapsedMs: number,
  durationMs = HEATMAP_TRANSITION_MS,
): number {
  const linear = Math.min(1, Math.max(0, elapsedMs / durationMs));
  return linear * linear * (3 - 2 * linear);
}

function isAtlasPick(value: unknown): value is AtlasPick {
  if (typeof value !== 'object' || value === null || !('kind' in value))
    return false;
  return value.kind === 'surface' || value.kind === 'observation';
}

function waitForReady(viewer: Viewer, group: FadeableGroup): Promise<void> {
  if (group.isReady()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const remove = viewer.scene.postRender.addEventListener(() => {
      if (!group.isReady()) return;
      clearTimeout(timeout);
      remove();
      resolve();
    });
    const timeout = window.setTimeout(() => {
      remove();
      reject(new Error('Cesium geometry build timed out'));
    }, 30_000);
    viewer.scene.requestRender();
  });
}

function animateSwap(
  viewer: Viewer,
  incoming: FadeableGroup,
  outgoing: FadeableGroup | null,
  reducedMotion: boolean,
): Promise<void> {
  if (reducedMotion) {
    incoming.setOpacity(1);
    if (outgoing) viewer.scene.primitives.remove(outgoing.collection);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const started = performance.now();
    const frame = (now: number) => {
      const progress = transitionProgress(now - started);
      incoming.setOpacity(progress);
      outgoing?.setOpacity(1 - progress);
      viewer.scene.requestRender();
      if (progress < 1) requestAnimationFrame(frame);
      else {
        if (outgoing) viewer.scene.primitives.remove(outgoing.collection);
        resolve();
      }
    };
    requestAnimationFrame(frame);
  });
}

class CesiumAtlasScene implements AtlasSceneController {
  readonly #viewer: Viewer;
  readonly #handler: ScreenSpaceEventHandler;
  readonly #pickListeners = new Set<(pick: AtlasPick | null) => void>();
  readonly #cameraListeners = new Set<(camera: CameraState) => void>();
  readonly #contextListeners = new Set<(status: ContextStatus) => void>();
  readonly #unbindKeyboard: () => void;
  readonly #removeMoveEnd: () => void;
  #surfaceArtifact: SurfaceArtifact | null = null;
  #surfaceGroup: ScientificPrimitiveGroup | null = null;
  #observationGroup: ObservationPrimitiveGroup | null = null;
  #contextLayer: ImageryLayer | null = null;
  #outlineSource: GeoJsonSource | null = null;
  #metric: Metric = 'post_mean';
  #layers = { ...DEFAULT_LAYERS };
  #elevation = false;
  #exaggeration = 1;
  #mode: ExplorerSceneMode = 'globe';
  #buildSequence = 0;
  #artifactSequence = 0;
  #destroyed = false;
  #contextStatus: ContextStatus = 'loading';
  #reducedMotion: boolean;

  constructor(container: HTMLElement, options: AtlasSceneOptions) {
    this.#reducedMotion = options.reducedMotion ?? false;
    this.#viewer = new Viewer(container, {
      animation: false,
      baseLayer: false,
      baseLayerPicker: false,
      fullscreenButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      navigationHelpButton: false,
      scene3DOnly: false,
      sceneModePicker: false,
      selectionIndicator: false,
      timeline: false,
      vrButton: false,
    });
    this.#styleScene();
    this.#unbindKeyboard = bindKeyboardCamera(this.#viewer, container);
    this.#removeMoveEnd = this.#viewer.camera.moveEnd.addEventListener(() => {
      const state = cameraState(this.#viewer);
      for (const listener of this.#cameraListeners) listener(state);
    });
    this.#handler = new ScreenSpaceEventHandler(this.#viewer.scene.canvas);
    this.#handler.setInputAction(
      (event: ScreenSpaceEventHandler.PositionedEvent) => {
        const picked = this.#viewer.scene.pick(event.position) as
          { id?: unknown } | undefined;
        const value = picked?.id;
        for (const listener of this.#pickListeners)
          listener(isAtlasPick(value) ? value : null);
      },
      ScreenSpaceEventType.LEFT_CLICK,
    );
    this.setCamera(HOME_CAMERA, !options.reducedMotion);
    void this.#loadContext(options);
  }

  #styleScene(): void {
    const scene = this.#viewer.scene;
    scene.backgroundColor = Color.fromCssColorString('#020712');
    scene.globe.baseColor = Color.fromCssColorString('#071b35');
    scene.globe.enableLighting = true;
    scene.globe.showGroundAtmosphere = true;
    scene.fog.enabled = true;
    scene.fog.density = 0.00012;
    scene.highDynamicRange = true;
    scene.postProcessStages.fxaa.enabled = true;
    scene.postProcessStages.bloom.enabled = true;
    scene.postProcessStages.bloom.uniforms.brightness = -0.18;
    scene.postProcessStages.bloom.uniforms.contrast = 92;
    this.#viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 1.5);
  }

  async #loadContext(options: AtlasSceneOptions): Promise<void> {
    const imageryUrl =
      options.contextImageryUrl ??
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    try {
      const provider = new UrlTemplateImageryProvider({
        credit: new Credit(
          '<a href="https://www.openstreetmap.org/copyright" target="_blank">© OpenStreetMap contributors</a>',
          true,
        ),
        enablePickFeatures: false,
        maximumLevel: 18,
        url: imageryUrl,
      });
      provider.errorEvent.addEventListener(() =>
        this.#setContextStatus('fallback'),
      );
      const contextLayer = new ImageryLayer(provider);
      this.#viewer.imageryLayers.add(contextLayer);
      contextLayer.alpha = 0.63;
      contextLayer.brightness = 0.55;
      contextLayer.contrast = 1.2;
      contextLayer.saturation = 0.48;
      contextLayer.show = this.#layers.context;
      this.#contextLayer = contextLayer;
      this.#setContextStatus('ready');
    } catch {
      this.#setContextStatus('fallback');
    }

    try {
      const source = await GeoJsonDataSource.load(options.naturalEarthUrl, {
        clampToGround: true,
        fill: Color.TRANSPARENT,
        stroke: Color.fromCssColorString('#4dc5df').withAlpha(0.46),
        strokeWidth: 1.2,
      });
      source.credit = new Credit(
        '<a href="https://www.naturalearthdata.com/" target="_blank">Natural Earth</a> (public domain)',
        true,
      );
      if (this.#destroyed) return;
      await this.#viewer.dataSources.add(source);
      source.show = this.#layers.context;
      this.#outlineSource = source;
    } catch {
      this.#setContextStatus('fallback');
    }
  }

  #setContextStatus(status: ContextStatus): void {
    this.#contextStatus = status;
    for (const listener of this.#contextListeners) listener(status);
  }

  async #replaceSurface(): Promise<void> {
    if (this.#surfaceArtifact === null) return;
    const sequence = ++this.#buildSequence;
    const incoming = buildSurfaceLayer(this.#surfaceArtifact, {
      elevation: this.#elevation && this.#mode !== 'map',
      exaggeration: this.#exaggeration,
      metric: this.#metric,
    });
    incoming.setOpacity(0);
    incoming.setVisibility(this.#layers.surface, this.#layers.support);
    this.#viewer.scene.primitives.add(incoming.collection);
    await waitForReady(this.#viewer, incoming);
    if (sequence !== this.#buildSequence || this.#destroyed) {
      this.#viewer.scene.primitives.remove(incoming.collection);
      return;
    }
    const outgoing = this.#surfaceGroup;
    this.#surfaceGroup = incoming;
    await animateSwap(this.#viewer, incoming, outgoing, this.#reducedMotion);
  }

  async setArtifact(
    surface: SurfaceArtifact,
    observations: ObservationArtifact,
  ): Promise<void> {
    const sequence = ++this.#artifactSequence;
    this.#surfaceArtifact = surface;
    const incomingObservations = buildObservationLayer(observations);
    incomingObservations.setOpacity(0);
    incomingObservations.collection.show = this.#layers.observations;
    this.#viewer.scene.primitives.add(incomingObservations.collection);
    const oldObservations = this.#observationGroup;
    await Promise.all([
      this.#replaceSurface(),
      waitForReady(this.#viewer, incomingObservations),
    ]);
    if (this.#destroyed || sequence !== this.#artifactSequence) {
      this.#viewer.scene.primitives.remove(incomingObservations.collection);
      return;
    }
    this.#observationGroup = incomingObservations;
    await animateSwap(
      this.#viewer,
      incomingObservations,
      oldObservations,
      this.#reducedMotion,
    );
    incomingObservations.collection.show = this.#layers.observations;
  }

  async setMetric(metric: Metric): Promise<void> {
    if (this.#metric === metric) return;
    this.#metric = metric;
    await this.#replaceSurface();
  }

  setLayerVisibility(layers: LayerVisibility): void {
    this.#layers = { ...layers };
    this.#surfaceGroup?.setVisibility(layers.surface, layers.support);
    if (this.#observationGroup)
      this.#observationGroup.collection.show = layers.observations;
    if (this.#contextLayer) this.#contextLayer.show = layers.context;
    if (this.#outlineSource) this.#outlineSource.show = layers.context;
    this.#viewer.scene.requestRender();
  }

  async setElevation(enabled: boolean, exaggeration: number): Promise<void> {
    this.#elevation = enabled;
    this.#exaggeration = exaggeration;
    await this.#replaceSurface();
  }

  async setSceneMode(
    mode: ExplorerSceneMode,
    reducedMotion: boolean,
  ): Promise<void> {
    this.#reducedMotion = reducedMotion;
    const target = {
      globe: SceneMode.SCENE3D,
      map: SceneMode.SCENE2D,
      perspective: SceneMode.COLUMBUS_VIEW,
    }[mode];
    this.#mode = mode;
    if (this.#viewer.scene.mode !== target) {
      await new Promise<void>((resolve) => {
        const remove = this.#viewer.scene.morphComplete.addEventListener(() => {
          remove();
          resolve();
        });
        const duration = reducedMotion ? 0 : 0.8;
        if (mode === 'globe') this.#viewer.scene.morphTo3D(duration);
        else if (mode === 'map') this.#viewer.scene.morphTo2D(duration);
        else this.#viewer.scene.morphToColumbusView(duration);
      });
    }
    if (this.#elevation) await this.#replaceSurface();
  }

  setCamera(camera: CameraState, animated: boolean): void {
    setCameraState(this.#viewer, camera, animated);
  }

  home(animated: boolean): void {
    setCameraState(this.#viewer, HOME_CAMERA, animated);
  }

  zoom(direction: 'in' | 'out'): void {
    const distance = Math.max(
      50_000,
      this.#viewer.camera.positionCartographic.height * 0.28,
    );
    if (direction === 'in') this.#viewer.camera.zoomIn(distance);
    else this.#viewer.camera.zoomOut(distance);
  }

  onPick(listener: (pick: AtlasPick | null) => void): () => void {
    this.#pickListeners.add(listener);
    return () => this.#pickListeners.delete(listener);
  }

  onCameraSettled(listener: (camera: CameraState) => void): () => void {
    this.#cameraListeners.add(listener);
    return () => this.#cameraListeners.delete(listener);
  }

  onContextStatus(listener: (status: ContextStatus) => void): () => void {
    this.#contextListeners.add(listener);
    listener(this.#contextStatus);
    return () => this.#contextListeners.delete(listener);
  }

  destroy(): void {
    if (this.#destroyed) return;
    this.#destroyed = true;
    this.#buildSequence += 1;
    this.#artifactSequence += 1;
    this.#unbindKeyboard();
    this.#removeMoveEnd();
    this.#handler.destroy();
    this.#viewer.destroy();
  }
}

export function createAtlasScene(
  container: HTMLElement,
  options: AtlasSceneOptions,
): AtlasSceneController {
  return new CesiumAtlasScene(container, options);
}
