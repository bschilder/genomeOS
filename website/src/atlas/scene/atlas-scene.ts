/** Cesium lifecycle and scientific-layer orchestration for Atlas design §11. */

import { SceneMode, Viewer } from 'cesium';

import type { ObservationArtifact, SurfaceArtifact } from '../contracts';
import type { Metric, PaletteId } from '../visual-encoding';
import type {
  BasemapId,
  CameraState,
  ExplorerSceneMode,
  LayerVisibility,
  TerrainId,
} from '../url-state';
import { bindKeyboardCamera, cameraState, setCameraState } from './camera';
import {
  ContextController,
  type ContextWarning,
  type ContextWarningUpdate,
} from './context-controller';
import { LayerCache } from './layer-cache';
import { HighlightLayer } from './highlight-layer';
import { GeographicOverlay } from './geographic-overlay';
import {
  buildObservationLayer,
  type ObservationPrimitiveGroup,
} from './observation-layer';
import { bindAtlasPicking } from './picking';
import {
  DEFAULT_LAYERS,
  DEFAULT_OBSERVATIONS,
  HOME_CAMERA,
  styleAtlasScene,
} from './scene-policy';
import {
  buildSurfaceLayer,
  type ScientificPrimitiveGroup,
} from './surface-layer';
import { animateSwap, waitForReady } from './scene-transition';
import type {
  AtlasPick,
  AtlasSceneController,
  AtlasSceneOptions,
  ContextStatus,
  ObservationPresentation,
  SceneCapabilities,
} from './types';

export { preferredAtlasPick } from './picking';
export { resolveElevationView } from './scene-policy';
export { transitionProgress } from './scene-transition';
export type {
  AtlasPick,
  AtlasSceneController,
  AtlasSceneOptions,
  ContextStatus,
  ObservationPresentation,
  SceneCapabilities,
} from './types';

interface PreparedSurfaceSwap {
  incoming: ScientificPrimitiveGroup;
  outgoing: ScientificPrimitiveGroup | null;
  sequence: number;
}

class CesiumAtlasScene implements AtlasSceneController {
  readonly #viewer: Viewer;
  readonly #pickListeners = new Set<(pick: AtlasPick | null) => void>();
  readonly #cameraListeners = new Set<(camera: CameraState) => void>();
  readonly #contextListeners = new Set<(status: ContextStatus) => void>();
  readonly #warningListeners = new Set<
    (warnings: readonly ContextWarning[]) => void
  >();
  readonly #warnings = new Map<ContextWarning['id'], ContextWarning>();
  readonly #unbindKeyboard: () => void;
  readonly #unbindPicking: () => void;
  readonly #removeMoveEnd: () => void;
  #surfaceArtifact: SurfaceArtifact | null = null;
  #observationArtifact: ObservationArtifact | null = null;
  #surfaceGroup: ScientificPrimitiveGroup | null = null;
  #observationGroup: ObservationPrimitiveGroup | null = null;
  readonly #surfaceCache = new LayerCache<ScientificPrimitiveGroup>(4);
  readonly #observationCache = new LayerCache<ObservationPrimitiveGroup>(3);
  readonly #contextController: ContextController;
  readonly #geographicOverlay: GeographicOverlay;
  readonly #highlightLayer: HighlightLayer;
  #metric: Metric = 'post_mean';
  #palette: PaletteId = 'genome';
  #surfaceOpacity = 0.86;
  #cellEdges = false;
  #observationStyle = { ...DEFAULT_OBSERVATIONS };
  #layers = { ...DEFAULT_LAYERS };
  #elevation = false;
  #exaggeration = 1;
  #mode: ExplorerSceneMode = 'globe';
  #buildSequence = 0;
  #artifactSequence = 0;
  #artifactIdentity = '';
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
      maximumRenderTimeChange: Number.POSITIVE_INFINITY,
      requestRenderMode: true,
      scene3DOnly: false,
      sceneModePicker: false,
      selectionIndicator: false,
      timeline: false,
      vrButton: false,
    });
    this.#contextController = new ContextController(
      this.#viewer,
      options.cesiumToken ?? '',
      options.contextImageryUrl ??
        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      (warning) => this.#setWarning(warning),
    );
    this.#geographicOverlay = new GeographicOverlay(this.#viewer);
    styleAtlasScene(this.#viewer);
    this.#highlightLayer = new HighlightLayer(this.#viewer.scene);
    this.#viewer.scene.primitives.add(this.#highlightLayer.collection);
    this.#unbindKeyboard = bindKeyboardCamera(this.#viewer, container);
    this.#removeMoveEnd = this.#viewer.camera.moveEnd.addEventListener(() => {
      const state = cameraState(this.#viewer);
      if (!state) return;
      for (const listener of this.#cameraListeners) listener(state);
    });
    this.#unbindPicking = bindAtlasPicking(
      this.#viewer.scene,
      (value) => {
        this.#highlightLayer.setSelection(value);
        for (const listener of this.#pickListeners) listener(value);
      },
      (value) => this.#highlightLayer.setHover(value, this.#reducedMotion),
    );
    this.setCamera(HOME_CAMERA, false);
    void this.#contextController.setBasemap('dark-streets');
    void this.#geographicOverlay
      .load(options.naturalEarthUrl)
      .then((status) => {
        if (!this.#destroyed) this.#setContextStatus(status);
      });
  }

  #setContextStatus(status: ContextStatus): void {
    this.#contextStatus = status;
    for (const listener of this.#contextListeners) listener(status);
  }

  #setWarning(warning: ContextWarningUpdate): void {
    if (warning.message) this.#warnings.set(warning.id, warning);
    else this.#warnings.delete(warning.id);
    const current = [...this.#warnings.values()];
    for (const listener of this.#warningListeners) listener(current);
  }

  async #prepareSurface(): Promise<PreparedSurfaceSwap | null> {
    if (this.#surfaceArtifact === null) return null;
    const sequence = ++this.#buildSequence;
    const elevated = this.#elevation && this.#mode !== 'map';
    const identity = this.#surfaceArtifact.artifact;
    const key = [
      identity.id,
      identity.model_version,
      identity.data_version,
      this.#metric,
      this.#palette,
      this.#cellEdges ? 'edges' : 'no-edges',
      elevated ? `raised-${this.#exaggeration}` : 'flat',
    ].join(':');
    let incoming = this.#surfaceCache.get(key);
    if (!incoming) {
      incoming = buildSurfaceLayer(this.#surfaceArtifact, {
        elevation: elevated,
        exaggeration: this.#exaggeration,
        cellEdges: this.#cellEdges,
        metric: this.#metric,
        opacity: this.#surfaceOpacity,
        palette: this.#palette,
      });
      this.#surfaceCache.set(key, incoming);
      this.#viewer.scene.primitives.add(incoming.collection);
    }
    incoming.collection.show = true;
    incoming.setCellEdges(this.#cellEdges);
    incoming.setSurfaceOpacity(this.#surfaceOpacity);
    incoming.setOpacity(0);
    await waitForReady(this.#viewer, incoming);
    if (sequence !== this.#buildSequence || this.#destroyed) {
      if (incoming !== this.#surfaceGroup) incoming.collection.show = false;
      return null;
    }
    return { incoming, outgoing: this.#surfaceGroup, sequence };
  }

  async #activateSurface(swap: PreparedSurfaceSwap): Promise<void> {
    const { incoming, outgoing, sequence } = swap;
    if (sequence !== this.#buildSequence || this.#destroyed) {
      if (incoming !== this.#surfaceGroup) incoming.collection.show = false;
      return;
    }
    if (outgoing === incoming) {
      incoming.setVisibility(this.#layers.surface, this.#layers.support);
      incoming.setOpacity(1);
      return;
    }
    this.#surfaceGroup = incoming;
    incoming.setVisibility(this.#layers.surface, this.#layers.support);
    await animateSwap(
      this.#viewer,
      incoming,
      outgoing,
      this.#reducedMotion,
      true,
    );
    this.#surfaceCache.prune(incoming, (group) => {
      this.#viewer.scene.primitives.remove(group.collection);
    });
  }

  async #replaceSurface(): Promise<void> {
    const swap = await this.#prepareSurface();
    if (swap) await this.#activateSurface(swap);
  }

  async #replaceScientificLayers(): Promise<void> {
    if (this.#surfaceArtifact)
      await this.setArtifact(this.#surfaceArtifact, this.#observationArtifact);
  }

  async setArtifact(
    surface: SurfaceArtifact,
    observations: ObservationArtifact | null,
  ): Promise<void> {
    const sequence = ++this.#artifactSequence;
    const artifactIdentity = [
      surface.artifact.id,
      surface.artifact.model_version,
      surface.artifact.data_version,
    ].join(':');
    if (this.#artifactIdentity && this.#artifactIdentity !== artifactIdentity)
      this.setSelection(null);
    this.#artifactIdentity = artifactIdentity;
    this.#surfaceArtifact = surface;
    this.#observationArtifact = observations;
    let incomingObservations: ObservationPrimitiveGroup | null = null;
    if (observations) {
      const identity = observations.artifact;
      const observationKey = [
        identity.id,
        identity.model_version,
        identity.data_version,
        this.#metric,
        this.#elevation && this.#mode !== 'map'
          ? `raised-${this.#exaggeration}`
          : 'flat',
        this.#observationStyle.shape,
        this.#observationStyle.colorVariable,
        this.#observationStyle.sizeVariable,
        ...this.#observationStyle.pointRange,
        ...this.#observationStyle.hemisphereRange,
      ].join(':');
      incomingObservations = this.#observationCache.get(observationKey) ?? null;
      if (!incomingObservations) {
        incomingObservations = buildObservationLayer(observations, {
          colorVariable: this.#observationStyle.colorVariable,
          elevation: this.#elevation && this.#mode !== 'map',
          exaggeration: this.#exaggeration,
          hemisphereRange: this.#observationStyle.hemisphereRange,
          metric: this.#metric,
          pointRange: this.#observationStyle.pointRange,
          samplingAreas: this.#observationStyle.samplingAreas,
          shape: this.#observationStyle.shape,
          sizeVariable: this.#observationStyle.sizeVariable,
          surface,
        });
        this.#observationCache.set(observationKey, incomingObservations);
        this.#viewer.scene.primitives.add(incomingObservations.collection);
      }
      incomingObservations.collection.show = true;
      incomingObservations.setOpacity(0);
    }
    const oldObservations = this.#observationGroup;
    const [surfaceSwap] = await Promise.all([
      this.#prepareSurface(),
      incomingObservations
        ? waitForReady(this.#viewer, incomingObservations)
        : Promise.resolve(),
    ]);
    if (
      !surfaceSwap ||
      this.#destroyed ||
      sequence !== this.#artifactSequence
    ) {
      if (
        incomingObservations &&
        incomingObservations !== this.#observationGroup
      )
        incomingObservations.collection.show = false;
      return;
    }
    let observationTransition = Promise.resolve();
    if (!incomingObservations) {
      this.#observationGroup = null;
      if (oldObservations) oldObservations.collection.show = false;
    } else if (oldObservations === incomingObservations) {
      incomingObservations.setVisibility(
        this.#layers.observations,
        this.#observationStyle.samplingAreas,
      );
      incomingObservations.setOpacity(1);
    } else if (this.#layers.observations) {
      this.#observationGroup = incomingObservations;
      observationTransition = animateSwap(
        this.#viewer,
        incomingObservations,
        oldObservations,
        this.#reducedMotion,
        true,
      );
    } else {
      this.#observationGroup = incomingObservations;
      incomingObservations.collection.show = false;
      incomingObservations.setOpacity(1);
      if (oldObservations) oldObservations.collection.show = false;
    }
    incomingObservations?.setVisibility(
      this.#layers.observations,
      this.#observationStyle.samplingAreas,
    );
    await Promise.all([
      this.#activateSurface(surfaceSwap),
      observationTransition,
    ]);
    if (incomingObservations) {
      this.#observationCache.prune(incomingObservations, (group) => {
        this.#viewer.scene.primitives.remove(group.collection);
      });
    }
    this.#highlightLayer.setArtifacts(
      surface,
      observations,
      this.#metric,
      this.#elevation && this.#mode !== 'map',
      this.#exaggeration,
    );
    this.#viewer.scene.primitives.raiseToTop(this.#highlightLayer.collection);
  }

  async setMetric(metric: Metric): Promise<void> {
    if (this.#metric === metric) return;
    this.#metric = metric;
    await this.#replaceScientificLayers();
  }

  async setSurfaceStyle(
    palette: PaletteId,
    opacity: number,
    cellEdges: boolean,
  ): Promise<void> {
    const paletteChanged = this.#palette !== palette;
    const edgesChanged = this.#cellEdges !== cellEdges;
    this.#palette = palette;
    this.#surfaceOpacity = opacity;
    this.#cellEdges = cellEdges;
    this.#surfaceGroup?.setSurfaceOpacity(opacity);
    this.#surfaceGroup?.setCellEdges(cellEdges);
    if (paletteChanged || edgesChanged) await this.#replaceSurface();
    this.#viewer.scene.requestRender();
  }

  async setObservationStyle(style: ObservationPresentation): Promise<void> {
    const renderingChanged =
      this.#observationStyle.colorVariable !== style.colorVariable ||
      this.#observationStyle.shape !== style.shape ||
      this.#observationStyle.sizeVariable !== style.sizeVariable ||
      this.#observationStyle.pointRange.join(':') !==
        style.pointRange.join(':') ||
      this.#observationStyle.hemisphereRange.join(':') !==
        style.hemisphereRange.join(':');
    this.#observationStyle = { ...style };
    if (renderingChanged) await this.#replaceScientificLayers();
    else
      this.#observationGroup?.setVisibility(
        this.#layers.observations,
        style.samplingAreas,
      );
    this.#viewer.scene.requestRender();
  }

  setBasemap(basemap: BasemapId): Promise<boolean> {
    return this.#contextController.setBasemap(basemap);
  }

  setTerrain(terrain: TerrainId): Promise<boolean> {
    return this.#contextController.setTerrain(terrain);
  }

  capabilities(): SceneCapabilities {
    return this.#contextController.capabilities();
  }

  setLayerVisibility(layers: LayerVisibility): void {
    this.#layers = { ...layers };
    this.#surfaceGroup?.setVisibility(layers.surface, layers.support);
    if (this.#observationGroup)
      this.#observationGroup.setVisibility(
        layers.observations,
        this.#observationStyle.samplingAreas,
      );
    this.#contextController.setVisible(layers.context);
    this.#geographicOverlay.setVisible(layers.context);
    this.#viewer.scene.requestRender();
  }

  async setElevation(enabled: boolean, exaggeration: number): Promise<void> {
    this.#elevation = enabled;
    this.#exaggeration = exaggeration;
    await this.#replaceScientificLayers();
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
      this.#viewer.camera.cancelFlight();
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
    if (this.#elevation) await this.#replaceScientificLayers();
  }

  setCamera(camera: CameraState, animated: boolean): void {
    setCameraState(this.#viewer, camera, animated);
  }

  setSelection(pick: AtlasPick | null): void {
    this.#highlightLayer.setSelection(pick);
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

  onWarning(
    listener: (warnings: readonly ContextWarning[]) => void,
  ): () => void {
    this.#warningListeners.add(listener);
    listener([...this.#warnings.values()]);
    return () => this.#warningListeners.delete(listener);
  }

  destroy(): void {
    if (this.#destroyed) return;
    this.#destroyed = true;
    this.#buildSequence += 1;
    this.#artifactSequence += 1;
    this.#unbindKeyboard();
    this.#unbindPicking();
    this.#removeMoveEnd();
    this.#viewer.destroy();
  }
}

export function createAtlasScene(
  container: HTMLElement,
  options: AtlasSceneOptions,
): AtlasSceneController {
  return new CesiumAtlasScene(container, options);
}
