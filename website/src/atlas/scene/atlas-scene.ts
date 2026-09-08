/** Cesium lifecycle and scientific-layer orchestration for Atlas design §11. */

import { SceneMode, Viewer } from 'cesium';

import type { ObservationArtifact, SurfaceArtifact } from '../contracts';
import type { Metric, PaletteId } from '../visual-encoding';
import type {
  BasemapId,
  CameraState,
  EdgeColorMode,
  ExplorerSceneMode,
  LayerVisibility,
  SurfaceGeometry,
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
  applyEarthOpacity,
  applyOceanColor,
  styleAtlasScene,
} from './scene-policy';
import {
  buildSurfaceLayer,
  type ScientificPrimitiveGroup,
} from './surface-layer';
import { animateSwap, animateValue, waitForReady } from './scene-transition';
import type {
  AtlasPick,
  AtlasHover,
  AtlasSceneController,
  AtlasSceneOptions,
  ContextStatus,
  ObservationPresentation,
  SceneCapabilities,
} from './types';

export { preferredAtlasPick } from './picking';
export { applyEarthOpacity } from './scene-policy';
export { applyOceanColor } from './scene-policy';
export { resolveElevationView } from './scene-policy';
export { transitionProgress } from './scene-transition';
export type {
  AtlasHover,
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
  readonly #hoverListeners = new Set<(hover: AtlasHover | null) => void>();
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
  #palette: PaletteId = 'rainbow';
  #surfaceOpacity = 0.58;
  #surfaceGeometry: SurfaceGeometry = 'triangles';
  #earthOpacity = 1;
  #cellEdges = false;
  #edgeColorMode: EdgeColorMode = 'matched';
  #edgeFixedColor = '#b9f5ff';
  #observationStyle = { ...DEFAULT_OBSERVATIONS };
  #layers = { ...DEFAULT_LAYERS };
  #elevation = false;
  #exaggeration = 1;
  #elevationFactor = 0;
  #elevationSequence = 0;
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
      (value) => {
        this.#highlightLayer.setHover(value?.pick ?? null, this.#reducedMotion);
        for (const listener of this.#hoverListeners) listener(value);
      },
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

  #targetElevationFactor(): number {
    return this.#elevation && this.#mode !== 'map' ? this.#exaggeration : 0;
  }

  async #prepareSurface(): Promise<PreparedSurfaceSwap | null> {
    if (this.#surfaceArtifact === null) return null;
    const sequence = ++this.#buildSequence;
    const elevationFactor = this.#targetElevationFactor();
    const identity = this.#surfaceArtifact.artifact;
    const key = [
      identity.id,
      identity.model_version,
      identity.data_version,
      this.#metric,
      this.#palette,
      this.#edgeColorMode,
      this.#edgeFixedColor,
      this.#surfaceGeometry,
    ].join(':');
    let incoming = this.#surfaceCache.get(key);
    if (!incoming) {
      incoming = buildSurfaceLayer(this.#surfaceArtifact, {
        elevation: elevationFactor > 0,
        exaggeration: elevationFactor,
        cellEdges: this.#cellEdges,
        edgeColorMode: this.#edgeColorMode,
        edgeFixedColor: this.#edgeFixedColor,
        geometry: this.#surfaceGeometry,
        metric: this.#metric,
        mode: this.#mode,
        opacity: this.#surfaceOpacity,
        palette: this.#palette,
      });
      this.#surfaceCache.set(key, incoming);
      this.#viewer.scene.primitives.add(incoming.collection);
    }
    incoming.collection.show = true;
    await incoming.setSceneMode(this.#mode);
    await incoming.setCellEdges(this.#cellEdges);
    incoming.setSurfaceOpacity(this.#surfaceOpacity);
    incoming.setOpacity(0);
    await waitForReady(this.#viewer, incoming);
    incoming.setElevationFactor(elevationFactor);
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
    this.#geographicOverlay.setSurface(surface, this.#metric);
    let incomingObservations: ObservationPrimitiveGroup | null = null;
    if (observations) {
      const identity = observations.artifact;
      const observationKey = [
        identity.id,
        identity.model_version,
        identity.data_version,
        this.#metric,
        this.#observationStyle.shape,
        this.#observationStyle.colorVariable,
        this.#observationStyle.solidColor,
        ...this.#observationStyle.gradient,
        this.#observationStyle.sizeVariable,
      ].join(':');
      incomingObservations = this.#observationCache.get(observationKey) ?? null;
      if (!incomingObservations) {
        incomingObservations = buildObservationLayer(observations, {
          colorVariable: this.#observationStyle.colorVariable,
          elevation: this.#targetElevationFactor() > 0,
          exaggeration: this.#targetElevationFactor(),
          gradient: this.#observationStyle.gradient,
          metric: this.#metric,
          opacity: this.#observationStyle.opacity,
          samplingAreaColor: this.#observationStyle.samplingAreaColor,
          sizeRange: this.#observationStyle.sizeRange,
          samplingAreas: this.#observationStyle.samplingAreas,
          shape: this.#observationStyle.shape,
          sizeVariable: this.#observationStyle.sizeVariable,
          solidColor: this.#observationStyle.solidColor,
          surface,
        });
        this.#observationCache.set(observationKey, incomingObservations);
        this.#viewer.scene.primitives.add(incomingObservations.collection);
      }
      incomingObservations.collection.show = true;
      incomingObservations.setSizeRange(this.#observationStyle.sizeRange);
      incomingObservations.setSamplingAreaColor(
        this.#observationStyle.samplingAreaColor,
      );
      incomingObservations.setElevationFactor(this.#targetElevationFactor());
      incomingObservations.setEarthOpacity(this.#earthOpacity);
      incomingObservations.setStyleOpacity(this.#observationStyle.opacity);
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
      this.#targetElevationFactor() > 0,
      this.#targetElevationFactor(),
    );
    this.#viewer.scene.primitives.raiseToTop(this.#highlightLayer.collection);
  }

  async setMetric(metric: Metric): Promise<void> {
    if (this.#metric === metric) return;
    this.#metric = metric;
    if (this.#surfaceArtifact)
      this.#geographicOverlay.setSurface(this.#surfaceArtifact, metric);
    await this.#replaceScientificLayers();
  }

  async setSurfaceStyle(
    palette: PaletteId,
    opacity: number,
    cellEdges: boolean,
    edgeColorMode: EdgeColorMode,
    edgeFixedColor: string,
    geometry: SurfaceGeometry,
  ): Promise<void> {
    const paletteChanged = this.#palette !== palette;
    const edgeStyleChanged =
      this.#edgeColorMode !== edgeColorMode ||
      this.#edgeFixedColor !== edgeFixedColor;
    const geometryChanged = this.#surfaceGeometry !== geometry;
    this.#palette = palette;
    this.#surfaceOpacity = opacity;
    this.#cellEdges = cellEdges;
    this.#edgeColorMode = edgeColorMode;
    this.#edgeFixedColor = edgeFixedColor;
    this.#surfaceGeometry = geometry;
    this.#surfaceGroup?.setSurfaceOpacity(opacity);
    if (paletteChanged || edgeStyleChanged || geometryChanged) {
      await this.#replaceSurface();
    } else {
      await this.#surfaceGroup?.setCellEdges(cellEdges);
    }
    this.#viewer.scene.requestRender();
  }

  async setObservationStyle(style: ObservationPresentation): Promise<void> {
    const opacityChanged = this.#observationStyle.opacity !== style.opacity;
    const sizeRangeChanged =
      this.#observationStyle.sizeRange.join(':') !== style.sizeRange.join(':');
    const samplingAreaColorChanged =
      this.#observationStyle.samplingAreaColor !== style.samplingAreaColor;
    const renderingChanged =
      this.#observationStyle.colorVariable !== style.colorVariable ||
      this.#observationStyle.solidColor !== style.solidColor ||
      this.#observationStyle.gradient.join(':') !== style.gradient.join(':') ||
      this.#observationStyle.shape !== style.shape ||
      this.#observationStyle.sizeVariable !== style.sizeVariable;
    this.#observationStyle = { ...style };
    if (opacityChanged) this.#observationGroup?.setStyleOpacity(style.opacity);
    if (samplingAreaColorChanged)
      this.#observationGroup?.setSamplingAreaColor(style.samplingAreaColor);
    if (renderingChanged) await this.#replaceScientificLayers();
    else {
      if (sizeRangeChanged)
        this.#observationGroup?.setSizeRange(style.sizeRange);
      this.#observationGroup?.setVisibility(
        this.#layers.observations,
        style.samplingAreas,
      );
    }
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
    this.#geographicOverlay.setVisible(layers.countries);
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
    this.#observationGroup?.setEarthOpacity(this.#earthOpacity);
    this.#highlightLayer.setEarthOpacity(this.#earthOpacity);
    this.#viewer.scene.requestRender();
  }

  setOceanColor(color: string): void {
    applyOceanColor(this.#viewer.scene.globe, color);
    this.#viewer.scene.requestRender();
  }

  setCountryBorderStyle(color: string, opacity: number): void {
    this.#geographicOverlay.setBorderStyle(color, opacity);
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
        this.#surfaceGroup?.setElevationFactor(factor);
        this.#observationGroup?.setElevationFactor(factor);
        this.#highlightLayer.setElevationStyle(factor > 0, factor);
        this.#geographicOverlay.setElevationFactor(factor);
      },
      () => sequence === this.#elevationSequence && !this.#destroyed,
    );
    if (sequence === this.#elevationSequence && !this.#destroyed) {
      this.#elevationFactor = target;
      this.#surfaceGroup?.setElevationFactor(target, true);
      this.#observationGroup?.setElevationFactor(target, true);
      this.#highlightLayer.setElevationStyle(target > 0, target);
      this.#geographicOverlay.setElevationFactor(target);
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
      await this.#surfaceGroup?.setSceneMode('perspective');
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
    await this.#surfaceGroup?.setSceneMode(mode);
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

  destroy(): void {
    if (this.#destroyed) return;
    this.#destroyed = true;
    this.#buildSequence += 1;
    this.#artifactSequence += 1;
    this.#elevationSequence += 1;
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
