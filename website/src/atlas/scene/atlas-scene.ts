/** Cesium lifecycle and scientific-layer orchestration for Atlas design §11 (spec 2026-10-07 §B.6). */

import { SceneMode, Viewer } from 'cesium';

import type {
  BasemapId,
  CameraState,
  EdgeColorMode,
  ExplorerSceneMode,
  LayerVisibility,
  SurfaceGeometry,
  TerrainId,
} from '../url-state';
import type { Metric, PaletteId } from '../visual-encoding';
import { bindKeyboardCamera, cameraState, setCameraState } from './camera';
import { revealFrameBudgetMs } from './chunk-scheduler';
import {
  ContextController,
  type ContextWarning,
  type ContextWarningUpdate,
} from './context-controller';
import { ContextOverlay } from './context-overlay';
import { HighlightLayer } from './highlight-layer';
import { bindAtlasPicking } from './picking';
import { RenderLoop } from './render-loop';
import { createMarkTracker, type MarkTracker } from './scene-marks';
import {
  DEFAULT_LAYERS,
  DEFAULT_OBSERVATIONS,
  HOME_CAMERA,
  applyEarthOpacity,
  applyOceanColor,
  hideSkyUntilReady,
  styleAtlasScene,
} from './scene-policy';
import { animateValue } from './scene-transition';
import { ScientificLayers, type ScientificStyle } from './scientific-layers';
import { createSurfacePickResolver } from './surface-pick';
import type {
  ArtifactLoad,
  AtlasHover,
  AtlasMark,
  AtlasPick,
  AtlasSceneController,
  AtlasSceneOptions,
  ContextStatus,
  DisplayedLayer,
  ObservationPresentation,
  SceneCapabilities,
  SceneProgressListener,
} from './types';

export { preferredAtlasPick } from './picking';
export { applyEarthOpacity } from './scene-policy';
export { applyOceanColor } from './scene-policy';
export { resolveElevationView } from './scene-policy';
export { raiseScientificOverlays } from './scientific-layers';
export { transitionProgress } from './scene-transition';
export type {
  ArtifactLoad,
  AtlasHover,
  AtlasMark,
  AtlasPick,
  AtlasSceneController,
  AtlasSceneOptions,
  ContextStatus,
  DisplayedLayer,
  ObservationPresentation,
  SceneCapabilities,
  SceneProgress,
  SceneProgressListener,
} from './types';

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

class CesiumAtlasScene implements AtlasSceneController {
  readonly #viewer: Viewer;
  readonly #pickListeners = new Set<(pick: AtlasPick | null) => void>();
  readonly #hoverListeners = new Set<(hover: AtlasHover | null) => void>();
  readonly #cameraListeners = new Set<(camera: CameraState) => void>();
  readonly #contextListeners = new Set<(status: ContextStatus) => void>();
  readonly #commitListeners = new Set<(artifactKey: string) => void>();
  readonly #warningListeners = new Set<
    (warnings: readonly ContextWarning[]) => void
  >();
  readonly #warnings = new Map<ContextWarning['id'], ContextWarning>();
  readonly #renderLoop: RenderLoop;
  readonly #unbindKeyboard: () => void;
  readonly #unbindPicking: () => void;
  readonly #removeMoveEnd: () => void;
  readonly #removeRenderError: () => void;
  readonly #removeMarks: () => void;
  readonly #contextController: ContextController;
  readonly #overlay: ContextOverlay;
  readonly #highlightLayer: HighlightLayer;
  readonly #marks: MarkTracker;
  readonly #layers: ScientificLayers;
  readonly #revealSky: () => void;
  readonly #naturalEarthUrl: string;
  #metric: Metric = 'post_mean';
  #palette: PaletteId = 'rainbow';
  #surfaceOpacity = 0.58;
  #surfaceGeometry: SurfaceGeometry = 'triangles';
  #earthOpacity = 1;
  #cellEdges = false;
  #edgeColorMode: EdgeColorMode = 'matched';
  #edgeFixedColor = '#b9f5ff';
  #observationStyle = { ...DEFAULT_OBSERVATIONS };
  #layerVisibility = { ...DEFAULT_LAYERS };
  #elevation = false;
  #exaggeration = 1;
  #elevationFactor = 0;
  #elevationSequence = 0;
  #mode: ExplorerSceneMode = 'globe';
  #destroyed = false;
  #contextStarted = false;
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
      // Cesium's own panel is a dead end, and its loop stops silently on errors outside
      // Scene.render; the Atlas loop sends every render error to the explorer's retry instead.
      showRenderLoopErrors: false,
      timeline: false,
      useDefaultRenderLoop: false,
      vrButton: false,
    });
    this.#renderLoop = new RenderLoop(() => {
      this.#viewer.resize();
      this.#viewer.render();
    });
    this.#removeRenderError = this.#viewer.scene.renderError.addEventListener(
      (_scene, error: unknown) => this.#renderLoop.fail(error),
    );
    this.#revealSky = hideSkyUntilReady(this.#viewer.scene);
    this.#marks = createMarkTracker(
      this.#viewer.scene,
      options.markTarget ?? null,
    );
    this.#contextController = new ContextController(
      this.#viewer,
      options.cesiumToken ?? '',
      options.contextImageryUrl ??
        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      (warning) => this.#setWarning(warning),
    );
    this.#overlay = new ContextOverlay({
      addCredit: (credit) => this.#viewer.creditDisplay.addStaticCredit(credit),
      scene: this.#viewer.scene,
      worker: options.worker,
    });
    this.#naturalEarthUrl = options.naturalEarthUrl;
    styleAtlasScene(this.#viewer);
    this.#highlightLayer = new HighlightLayer(this.#viewer.scene);
    this.#viewer.scene.primitives.add(this.#highlightLayer.collection);
    this.#layers = new ScientificLayers({
      frameBudgetMs:
        options.frameBudgetMs ??
        revealFrameBudgetMs(window.matchMedia('(pointer: coarse)').matches),
      highlight: this.#highlightLayer,
      marks: this.#marks,
      onCommit: (artifactKey) => this.#commit(artifactKey),
      scene: this.#viewer.scene,
      style: () => this.#scientificStyle(),
      worker: options.worker,
    });
    this.#removeMarks = this.#marks.onMark((mark) => {
      if (mark === 'ready') this.#revealSky();
      if (mark === 'surface-visible') this.#startContext();
    });
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
      (value) => {
        this.#highlightLayer.setHover(value?.pick ?? null, this.#reducedMotion);
        for (const listener of this.#hoverListeners) listener(value);
      },
      createSurfacePickResolver(this.#viewer.scene, {
        factor: () => this.#elevationFactor,
        geometry: () =>
          this.#layers.displayedLayer()?.geometry ?? this.#surfaceGeometry,
        metric: () => this.#layers.displayedLayer()?.metric ?? this.#metric,
        target: () => this.#layers.pickTarget(),
      }),
    );
    this.setCamera(HOME_CAMERA, false);
    void this.#contextController.setBasemap('dark-streets');
    this.#renderLoop.start();
  }

  #scientificStyle(): ScientificStyle {
    return {
      cellEdges: this.#cellEdges,
      earthOpacity: this.#earthOpacity,
      edgeColorMode: this.#edgeColorMode,
      edgeFixedColor: this.#edgeFixedColor,
      elevationFactor: this.#elevationFactor,
      geometry: this.#surfaceGeometry,
      layers: this.#layerVisibility,
      metric: this.#metric,
      mode: this.#mode,
      observationStyle: this.#observationStyle,
      palette: this.#palette,
      reducedMotion: this.#reducedMotion,
      surfaceOpacity: this.#surfaceOpacity,
    };
  }

  #commit(artifactKey: string): void {
    this.#overlay.setSurface(
      artifactKey,
      this.#layers.displayedLayer()?.metric ?? this.#metric,
    );
    this.#overlay.setElevationFactor(this.#elevationFactor, true);
    for (const listener of this.#commitListeners) listener(artifactKey);
  }

  #startContext(): void {
    if (this.#contextStarted || this.#destroyed) return;
    this.#contextStarted = true;
    void this.#overlay.load(this.#naturalEarthUrl).then((status) => {
      if (this.#destroyed) return;
      if (status === 'ready') this.#marks.queue('context-ready');
      this.#setContextStatus(status);
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

  #targetElevationFactor(): number {
    return this.#elevation && this.#mode !== 'map' ? this.#exaggeration : 0;
  }

  async setArtifact(
    load: ArtifactLoad,
    progress?: SceneProgressListener,
  ): Promise<void> {
    try {
      await this.#layers.setArtifact(load, progress);
    } catch (error) {
      if (!isAbortError(error)) {
        this.#revealSky();
        this.#startContext();
      }
      throw error;
    }
  }

  async setMetric(
    metric: Metric,
    progress?: SceneProgressListener,
  ): Promise<void> {
    if (this.#metric === metric) return;
    this.#metric = metric;
    await this.#layers.rebuild(progress);
  }

  async setSurfaceStyle(
    palette: PaletteId,
    opacity: number,
    cellEdges: boolean,
    edgeColorMode: EdgeColorMode,
    edgeFixedColor: string,
    geometry: SurfaceGeometry,
    progress?: SceneProgressListener,
  ): Promise<void> {
    const rebuild =
      this.#palette !== palette || this.#surfaceGeometry !== geometry;
    const edgeStyleChanged =
      this.#edgeColorMode !== edgeColorMode ||
      this.#edgeFixedColor !== edgeFixedColor;
    this.#palette = palette;
    this.#surfaceOpacity = opacity;
    this.#cellEdges = cellEdges;
    this.#edgeColorMode = edgeColorMode;
    this.#edgeFixedColor = edgeFixedColor;
    this.#surfaceGeometry = geometry;
    this.#layers.setSurfaceOpacity(opacity);
    if (rebuild) await this.#layers.rebuild(progress);
    else if (edgeStyleChanged) await this.#layers.setEdgeStyle();
    else await this.#layers.setCellEdges(cellEdges);
    this.#viewer.scene.requestRender();
  }

  async setObservationStyle(
    style: ObservationPresentation,
    progress?: SceneProgressListener,
  ): Promise<void> {
    const renderingChanged =
      this.#observationStyle.colorVariable !== style.colorVariable ||
      this.#observationStyle.solidColor !== style.solidColor ||
      this.#observationStyle.gradient.join(':') !== style.gradient.join(':') ||
      this.#observationStyle.shape !== style.shape ||
      this.#observationStyle.sizeVariable !== style.sizeVariable;
    this.#observationStyle = { ...style };
    if (renderingChanged) await this.#layers.rebuild(progress);
    else this.#layers.setObservationAppearance(style, this.#layerVisibility);
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
    this.#layerVisibility = { ...layers };
    this.#layers.setVisibility(layers, this.#observationStyle.samplingAreas);
    this.#contextController.setVisible(layers.context);
    this.#overlay.setVisible(layers.countries);
    this.#viewer.scene.requestRender();
  }

  setMapPresentation(
    basemapOpacity: number,
    basemapBrightness: number,
    dayNightLighting: boolean,
  ): void {
    this.#contextController.setAppearance(basemapOpacity, basemapBrightness);
    this.#viewer.scene.globe.enableLighting = dayNightLighting;
    this.#viewer.scene.requestRender();
  }

  setEarthOpacity(opacity: number): void {
    this.#earthOpacity = Math.min(1, Math.max(0.15, opacity));
    applyEarthOpacity(this.#viewer.scene.globe, this.#earthOpacity);
    this.#layers.setEarthOpacity(this.#earthOpacity);
    this.#highlightLayer.setEarthOpacity(this.#earthOpacity);
    this.#viewer.scene.requestRender();
  }

  setOceanColor(color: string): void {
    applyOceanColor(this.#viewer.scene.globe, color);
    this.#viewer.scene.requestRender();
  }

  setCountryBorderStyle(color: string, opacity: number): void {
    this.#overlay.setBorderStyle(color, opacity);
  }

  async setElevation(enabled: boolean, exaggeration: number): Promise<void> {
    this.#elevation = enabled;
    this.#exaggeration = exaggeration;
    const target = this.#targetElevationFactor();
    const sequence = ++this.#elevationSequence;
    await animateValue(
      this.#viewer,
      this.#elevationFactor,
      target,
      this.#reducedMotion,
      (factor) => {
        this.#elevationFactor = factor;
        this.#layers.setElevationFactor(factor);
        this.#highlightLayer.setElevationStyle(factor > 0, factor);
        this.#overlay.setElevationFactor(factor);
      },
      () => sequence === this.#elevationSequence && !this.#destroyed,
    );
    if (sequence === this.#elevationSequence && !this.#destroyed) {
      this.#elevationFactor = target;
      this.#layers.setElevationFactor(target, true);
      this.#highlightLayer.setElevationStyle(target > 0, target);
      this.#overlay.setElevationFactor(target, true);
      this.#viewer.scene.requestRender();
    }
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
      await this.#layers.setSceneMode('perspective');
      await this.#overlay.setSceneMode('perspective');
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
    await this.#layers.setSceneMode(mode);
    await this.#overlay.setSceneMode(mode);
    await this.setElevation(this.#elevation, this.#exaggeration);
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

  displayedLayer(): DisplayedLayer | null {
    return this.#layers.displayedLayer();
  }

  markValuesReady(artifactKey: string): void {
    this.#layers.markValuesReady(artifactKey);
  }

  removeSurface(artifactKey: string): void {
    this.#layers.removeSurface(artifactKey);
  }

  onCommit(listener: (artifactKey: string) => void): () => void {
    this.#commitListeners.add(listener);
    return () => this.#commitListeners.delete(listener);
  }

  onMark(listener: (mark: AtlasMark) => void): () => void {
    return this.#marks.onMark(listener);
  }

  onPick(listener: (pick: AtlasPick | null) => void): () => void {
    this.#pickListeners.add(listener);
    return () => this.#pickListeners.delete(listener);
  }

  onHover(listener: (hover: AtlasHover | null) => void): () => void {
    this.#hoverListeners.add(listener);
    return () => this.#hoverListeners.delete(listener);
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

  onRenderError(listener: (error: unknown) => void): () => void {
    return this.#renderLoop.onError(listener);
  }

  destroy(): void {
    if (this.#destroyed) return;
    this.#destroyed = true;
    this.#elevationSequence += 1;
    this.#renderLoop.stop();
    this.#layers.destroy();
    this.#removeMarks();
    this.#marks.destroy();
    this.#unbindKeyboard();
    this.#unbindPicking();
    this.#removeMoveEnd();
    this.#removeRenderError();
    this.#viewer.destroy();
  }
}

export function createAtlasScene(
  container: HTMLElement,
  options: AtlasSceneOptions,
): AtlasSceneController {
  return new CesiumAtlasScene(container, options);
}
