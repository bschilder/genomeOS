/** Cold progressive reveal and atomic swaps of scientific layers for Atlas design §11
 * (spec 2026-10-07 §B.6.8; Cesium explorer design §9 and §12).
 *
 * When nothing scientific is displayed (the cold load, or a scene recreated
 * by "Retry globe") observations appear first and surface chunks appear with
 * their masks as the scheduler admits them. Whenever a layer is displayed,
 * every replacement is built in a shown collection at opacity 0 and becomes
 * visible in one `animateSwap` that also retires the outgoing surface,
 * support and observations. The commit callback fires at that swap, so the
 * legend, inspector and readiness attributes change with the pixels.
 */

import {
  Cartesian2,
  Ellipsoid,
  Math as CesiumMath,
  type PrimitiveCollection,
  type Scene,
} from 'cesium';

import type { ObservationArtifact } from '../contracts';
import type { SurfaceArtifact } from '../surface-columns';
import type {
  EdgeColorMode,
  ExplorerSceneMode,
  LayerVisibility,
  SurfaceGeometry,
} from '../url-state';
import type { Metric, PaletteId } from '../visual-encoding';
import type { AtlasWorkerClient } from '../worker/client';
import type { BuildChunksBody, ChunkMessage } from '../worker/protocol';
import { createMessageQueue, scheduleChunks } from './chunk-scheduler';
import { LayerCache } from './layer-cache';
import {
  buildObservationLayer,
  observationHeightsFromBuffers,
  type ObservationPrimitiveGroup,
  type ObservationSurfaceHeights,
} from './observation-layer';
import { REVEAL_ATTRIBUTE, type MarkTracker } from './scene-marks';
import { animateSwap, fadeTogether, waitForReady } from './scene-transition';
import {
  createSurfaceChunkGroup,
  type SurfaceChunkGroup,
} from './surface-chunk-layer';
import {
  columnarHeightSource,
  type SurfaceHeightSource,
} from './surface-heights';
import type { PickTarget } from './surface-pick';
import type {
  ArtifactLoad,
  AtlasMark,
  DisplayedLayer,
  ObservationPresentation,
  SceneProgressListener,
} from './types';

export interface ScientificStyle {
  metric: Metric;
  palette: PaletteId;
  geometry: SurfaceGeometry;
  surfaceOpacity: number;
  cellEdges: boolean;
  edgeColorMode: EdgeColorMode;
  edgeFixedColor: string;
  observationStyle: ObservationPresentation;
  layers: LayerVisibility;
  mode: ExplorerSceneMode;
  elevationFactor: number;
  earthOpacity: number;
  reducedMotion: boolean;
}

export interface ScientificHighlight {
  readonly collection: PrimitiveCollection;
  setArtifacts(
    surface: SurfaceHeightSource | null,
    observations: ObservationArtifact | null,
    metric: Metric,
    elevation: boolean,
    exaggeration: number,
  ): void;
}

export type ScientificScene = Pick<
  Scene,
  | 'camera'
  | 'canvas'
  | 'postRender'
  | 'preUpdate'
  | 'primitives'
  | 'requestRender'
>;

export interface ScientificLayersOptions {
  scene: ScientificScene;
  worker: Pick<AtlasWorkerClient, 'buildChunks' | 'buildEdges' | 'recolour'>;
  highlight: ScientificHighlight;
  marks: MarkTracker;
  style: () => ScientificStyle;
  frameBudgetMs: number;
  onCommit: (artifactKey: string) => void;
  perf?: { mark(name: string, options?: PerformanceMarkOptions): unknown };
}

interface Displayed {
  artifactKey: string;
  artifactId: string;
  surface: SurfaceArtifact;
  observations: ObservationArtifact | null;
  group: SurfaceChunkGroup | null;
  observationGroup: ObservationPrimitiveGroup | null;
  metric: Metric;
  palette: PaletteId;
  geometry: SurfaceGeometry;
}

interface Epoch {
  artifactKey: string;
  group: SurfaceChunkGroup | null;
  observationGroup: ObservationPrimitiveGroup | null;
  streamDone: boolean;
}

interface LiveGroup {
  collection: { show: boolean };
  opacity(): number;
}

class SupersededBuild extends Error {
  constructor() {
    super('Scientific layer build was superseded');
    this.name = 'AbortError';
  }
}

export function raiseScientificOverlays(
  primitives: PrimitiveCollection,
  observationLayer: PrimitiveCollection | null,
  highlightLayer: PrimitiveCollection,
): void {
  if (observationLayer?.isDestroyed() === false)
    primitives.raiseToTop(observationLayer);
  if (!highlightLayer.isDestroyed()) primitives.raiseToTop(highlightLayer);
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

function shown(group: LiveGroup): boolean {
  return group.collection.show && group.opacity() > 0;
}

function surfaceKeyFor(artifactKey: string, style: ScientificStyle): string {
  return [artifactKey, style.metric, style.palette, style.geometry].join(':');
}

function observationKeyFor(
  artifactKey: string,
  style: ObservationPresentation,
): string {
  return [
    artifactKey,
    style.shape,
    style.colorVariable,
    style.solidColor,
    ...style.gradient,
    style.sizeVariable,
  ].join(':');
}

function edgeStyleKey(style: ScientificStyle): string {
  return `${style.edgeColorMode}:${style.edgeFixedColor}`;
}

function observationPoints(
  observations: ObservationArtifact | null,
): Float64Array | null {
  return observations
    ? Float64Array.from(
        observations.observations.flatMap(({ lat, lon }) => [lon, lat]),
      )
    : null;
}

export class ScientificLayers {
  readonly #options: ScientificLayersOptions;
  readonly #perf: NonNullable<ScientificLayersOptions['perf']>;
  readonly #surfaces = new LayerCache<SurfaceChunkGroup>(4);
  readonly #observations = new LayerCache<ObservationPrimitiveGroup>(3);
  readonly #heights = new WeakMap<
    SurfaceChunkGroup,
    ObservationSurfaceHeights
  >();
  readonly #edgeStyles = new WeakMap<SurfaceChunkGroup, string>();
  readonly #ids = new Map<LiveGroup, string>();
  readonly #valuesReady = new Set<string>();
  readonly #removeMarkListener: () => void;
  #displayed: Displayed | null = null;
  #epoch: Epoch | null = null;
  /** The cold epoch being revealed, picked until it commits or is discarded. */
  #revealing: { epoch: Epoch; surface: SurfaceArtifact | null } | null = null;
  /**
   * What `rebuild()` replays: the latest request, pending or not, so a style
   * change during a swap rebuilds the incoming artifact. Once that request
   * fails it falls back to the displayed artifact.
   */
  #current: Omit<ArtifactLoad, 'lookAt'> | null = null;
  /**
   * The newest `setArtifact` call's outcome. A call that a later call for the same artifact
   * supersedes (a restyle's `rebuild()` replays the pending request) settles with that later
   * call, so its caller never sees success while the replacement alone carries the outcome.
   */
  #newest: { artifactKey: string; outcome: Promise<void> } | null = null;
  #sequence = 0;
  #build: AbortController | null = null;
  #edgeBuild: AbortController | null = null;
  #destroyed = false;

  constructor(options: ScientificLayersOptions) {
    this.#options = options;
    this.#perf = options.perf ?? performance;
    options.marks.setProbe(() => this.#probe());
    options.marks.setDisplayed(() =>
      [...this.#ids].filter(([group]) => shown(group)).map(([, id]) => id),
    );
    this.#removeMarkListener = options.marks.onMark((mark) => {
      if (mark === 'surface-visible') this.#startEdges();
    });
  }

  displayedLayer(): DisplayedLayer | null {
    const displayed = this.#displayed;
    return displayed
      ? {
          artifactKey: displayed.artifactKey,
          geometry: displayed.geometry,
          metric: displayed.metric,
          palette: displayed.palette,
        }
      : null;
  }

  pickTarget(): PickTarget | null {
    const displayed = this.#displayed;
    if (displayed) {
      // The incoming groups sit at opacity 0, but a translucent depth pick writes depth
      // whatever the alpha, so both are hidden for that pass (§B.6.6).
      const hidden: PrimitiveCollection[] = [];
      const incoming = this.#epoch?.group;
      if (incoming && incoming !== displayed.group)
        hidden.push(incoming.collection);
      const incomingObservations = this.#epoch?.observationGroup;
      if (
        incomingObservations &&
        incomingObservations !== displayed.observationGroup
      )
        hidden.push(incomingObservations.collection);
      return {
        artifactKey: displayed.artifactKey,
        hidden,
        surface: displayed.surface,
      };
    }
    const revealing = this.#revealing;
    return revealing?.surface
      ? {
          artifactKey: revealing.epoch.artifactKey,
          hidden: [],
          surface: revealing.surface,
        }
      : null;
  }

  /**
   * Shows `load`. A call superseded by a call for another artifact resolves; one superseded by a
   * call for the same artifact (a rebuild) settles with the newest such call.
   */
  setArtifact(
    load: ArtifactLoad,
    progress?: SceneProgressListener,
  ): Promise<void> {
    const outcome: Promise<void> = this.#show(load, progress).then(
      (superseded) => {
        const newest = this.#newest;
        if (
          superseded &&
          !this.#destroyed &&
          newest &&
          newest.outcome !== outcome &&
          newest.artifactKey === load.artifactKey
        )
          return newest.outcome;
      },
    );
    this.#newest = { artifactKey: load.artifactKey, outcome };
    return outcome;
  }

  /** Resolves true when a newer call superseded this one, false once it is shown. */
  async #show(
    load: ArtifactLoad,
    progress?: SceneProgressListener,
  ): Promise<boolean> {
    const sequence = ++this.#sequence;
    this.#build?.abort();
    const abort = new AbortController();
    this.#build = abort;
    const cold = this.#displayed === null;
    const epoch: Epoch = {
      artifactKey: load.artifactKey,
      group: null,
      observationGroup: null,
      streamDone: false,
    };
    this.#epoch = epoch;
    this.#current = {
      artifactId: load.artifactId,
      artifactKey: load.artifactKey,
      observations: load.observations,
      surface: load.surface,
    };
    this.#options.marks.beginEpoch();
    let partial: SurfaceChunkGroup | null = null;
    const assertCurrent = () => {
      if (this.#destroyed || sequence !== this.#sequence)
        throw new SupersededBuild();
    };
    try {
      progress?.({ detail: 'Building measured points', progress: null });
      const observations = await load.observations;
      assertCurrent();
      const observationGroup = observations
        ? this.#observationGroupFor(load, observations)
        : null;
      epoch.observationGroup = observationGroup;
      if (
        observationGroup &&
        observationGroup !== this.#displayed?.observationGroup
      ) {
        observationGroup.collection.show = true;
        observationGroup.setOpacity(cold ? 1 : 0);
        if (cold) {
          const style = this.#options.style();
          observationGroup.setVisibility(
            style.layers.observations,
            style.observationStyle.samplingAreas,
          );
          this.#revealing = { epoch, surface: null };
        }
      }
      this.#raiseOverlays(observationGroup);
      this.#options.scene.requestRender();

      const surface = await load.surface;
      assertCurrent();
      if (cold) this.#revealing = { epoch, surface };
      const style = this.#options.style();
      const key = surfaceKeyFor(load.artifactKey, style);
      let group = this.#surfaces.get(key) ?? null;
      if (group) {
        epoch.group = group;
        if (group !== this.#displayed?.group) {
          group.collection.show = true;
          group.setOpacity(cold ? 1 : 0);
        }
        const heights = this.#heights.get(group);
        if (
          heights &&
          observationGroup &&
          observationGroup !== this.#displayed?.observationGroup
        )
          observationGroup.setSurfaceHeights(heights);
      } else {
        group = partial = this.#createGroup(load, style, cold);
        epoch.group = group;
        await this.#stream({
          group,
          load,
          observationGroup,
          observations,
          progress,
          signal: abort.signal,
          style,
          surface,
        });
        assertCurrent();
        this.#surfaces.set(key, group);
        partial = null;
      }
      epoch.streamDone = true;
      this.#options.scene.requestRender();
      await waitForReady({ scene: this.#options.scene }, group, (value) =>
        progress?.({ detail: 'Preparing surface geometry', progress: value }),
      );
      assertCurrent();
      await this.#commit({
        cold,
        group,
        load,
        observationGroup,
        observations,
        progress,
        surface,
      });
      // A request made during the swap animation began a new epoch; this `ready` is not its own.
      if (sequence === this.#sequence) this.#options.marks.queue('ready');
      return false;
    } catch (error) {
      this.#discard(epoch, partial);
      if (
        error instanceof SupersededBuild ||
        (sequence !== this.#sequence && isAbortError(error))
      )
        return true;
      // A rebuild must not replay a request that failed; it restyles what is displayed.
      if (sequence === this.#sequence) this.#current = this.#displayedLoad();
      throw error;
    }
  }

  async rebuild(progress?: SceneProgressListener): Promise<void> {
    const current = this.#current;
    if (!current) return;
    await this.setArtifact({ ...current }, progress);
  }

  setSurfaceOpacity(opacity: number): void {
    this.#displayed?.group?.setSurfaceOpacity(opacity);
    this.#options.scene.requestRender();
  }

  setVisibility(layers: LayerVisibility, samplingAreas: boolean): void {
    const displayed = this.#displayed;
    const groups = displayed
      ? { group: displayed.group, observationGroup: displayed.observationGroup }
      : {
          group: this.#epoch?.group ?? null,
          observationGroup: this.#epoch?.observationGroup ?? null,
        };
    groups.group?.setVisibility(layers.surface, layers.support);
    groups.observationGroup?.setVisibility(layers.observations, samplingAreas);
    this.#options.scene.requestRender();
  }

  setObservationAppearance(
    style: ObservationPresentation,
    layers: LayerVisibility,
  ): void {
    for (const group of this.#observationGroupsInView()) {
      group.setStyleOpacity(style.opacity);
      group.setSamplingAreaColor(style.samplingAreaColor);
      group.setSizeRange(style.sizeRange);
      group.setVisibility(layers.observations, style.samplingAreas);
    }
    this.#options.scene.requestRender();
  }

  setEarthOpacity(opacity: number): void {
    for (const group of this.#observationGroupsInView())
      group.setEarthOpacity(opacity);
  }

  setElevationFactor(factor: number, force = false): void {
    const displayed = this.#displayed;
    if (displayed) {
      displayed.group?.setElevationFactor(factor, force);
      displayed.observationGroup?.setElevationFactor(factor, force);
      return;
    }
    const epoch = this.#epoch;
    // A cold epoch's group follows the factor once its marker heights are applied, or at once
    // when the artifact has no observations (`epoch.group` is set only after observations
    // resolve, so a null observation group then means there are none).
    if (
      epoch?.group &&
      (this.#heights.has(epoch.group) || epoch.observationGroup === null)
    )
      epoch.group.setElevationFactor(factor, force);
    epoch?.observationGroup?.setElevationFactor(factor, force);
  }

  async setSceneMode(mode: ExplorerSceneMode): Promise<void> {
    await this.#displayed?.group?.setSceneMode(mode);
  }

  async setCellEdges(visible: boolean): Promise<void> {
    const displayed = this.#displayed;
    const group = displayed?.group;
    if (!displayed || !group) return;
    await group.setCellEdges(visible);
    if (visible) await this.#buildEdges(displayed, group);
    else this.#options.marks.clear('edges-ready');
  }

  async setEdgeStyle(): Promise<void> {
    const displayed = this.#displayed;
    const group = displayed?.group;
    if (!displayed || !group) return;
    const style = this.#options.style();
    if (this.#edgeStyles.get(group) === edgeStyleKey(style)) return;
    group.edges.reset();
    this.#edgeStyles.delete(group);
    this.#options.marks.clear('edges-ready');
    if (style.cellEdges) await this.#buildEdges(displayed, group);
  }

  markValuesReady(artifactKey: string): void {
    this.#valuesReady.add(artifactKey);
    if (this.#displayed?.artifactKey === artifactKey)
      this.#options.marks.queue('values-ready');
  }

  removeSurface(artifactKey: string): void {
    const displayed = this.#displayed;
    const group = displayed?.group;
    if (!displayed || displayed.artifactKey !== artifactKey || !group) return;
    displayed.group = null;
    this.#surfaces.delete(group);
    this.#dispose(group);
    this.#options.marks.clear('values-ready');
    this.#options.marks.clear('edges-ready');
    this.#options.highlight.setArtifacts(
      null,
      displayed.observations,
      displayed.metric,
      false,
      0,
    );
    this.#options.scene.requestRender();
  }

  destroy(): void {
    this.#destroyed = true;
    this.#build?.abort();
    this.#edgeBuild?.abort();
    this.#removeMarkListener();
  }

  #probe(): AtlasMark[] {
    const epoch = this.#epoch;
    if (!epoch) return [];
    const marks: AtlasMark[] = [];
    if (epoch.observationGroup && shown(epoch.observationGroup))
      marks.push('observations-visible');
    const group = epoch.group;
    if (group && shown(group) && group.readyChunkCount() > 0)
      marks.push('surface-first-chunk');
    if (group && epoch.streamDone && shown(group) && group.isReady())
      marks.push('surface-visible');
    return marks;
  }

  /** The displayed observation group and, during a swap or a cold reveal, the incoming one. */
  #observationGroupsInView(): ObservationPrimitiveGroup[] {
    const groups = new Set<ObservationPrimitiveGroup>();
    if (this.#displayed?.observationGroup)
      groups.add(this.#displayed.observationGroup);
    if (this.#epoch?.observationGroup) groups.add(this.#epoch.observationGroup);
    return [...groups];
  }

  #displayedLoad(): Omit<ArtifactLoad, 'lookAt'> | null {
    const displayed = this.#displayed;
    return displayed
      ? {
          artifactId: displayed.artifactId,
          artifactKey: displayed.artifactKey,
          observations: Promise.resolve(displayed.observations),
          surface: Promise.resolve(displayed.surface),
        }
      : null;
  }

  #observationGroupFor(
    load: ArtifactLoad,
    observations: ObservationArtifact,
  ): ObservationPrimitiveGroup {
    const style = this.#options.style();
    const presentation = style.observationStyle;
    const key = observationKeyFor(load.artifactKey, presentation);
    let group = this.#observations.get(key);
    if (!group) {
      group = buildObservationLayer(observations, {
        artifactKey: load.artifactKey,
        colorVariable: presentation.colorVariable,
        elevation: style.elevationFactor > 0,
        exaggeration: style.elevationFactor,
        gradient: presentation.gradient,
        heights: null,
        opacity: presentation.opacity,
        samplingAreaColor: presentation.samplingAreaColor,
        samplingAreas: presentation.samplingAreas,
        shape: presentation.shape,
        sizeRange: presentation.sizeRange,
        sizeVariable: presentation.sizeVariable,
        solidColor: presentation.solidColor,
      });
      this.#observations.set(key, group);
      this.#ids.set(group, load.artifactId);
      this.#options.scene.primitives.add(group.collection);
    }
    group.setSizeRange(presentation.sizeRange);
    group.setSamplingAreaColor(presentation.samplingAreaColor);
    group.setElevationFactor(style.elevationFactor, true);
    group.setEarthOpacity(style.earthOpacity);
    group.setStyleOpacity(presentation.opacity);
    return group;
  }

  #createGroup(
    load: ArtifactLoad,
    style: ScientificStyle,
    cold: boolean,
  ): SurfaceChunkGroup {
    const group = createSurfaceChunkGroup({
      artifactKey: load.artifactKey,
      cellEdges: style.cellEdges,
      elevationFactor: 0,
      geometry: style.geometry,
      requestRender: () => this.#options.scene.requestRender(),
      surfaceOpacity: style.surfaceOpacity,
    });
    group.setOpacity(cold ? 1 : 0);
    group.setVisibility(style.layers.surface, style.layers.support);
    group.collection.show = true;
    this.#ids.set(group, load.artifactId);
    this.#options.scene.primitives.add(group.collection);
    this.#raiseOverlays(this.#epoch?.observationGroup ?? null);
    return group;
  }

  async #stream(input: {
    group: SurfaceChunkGroup;
    load: ArtifactLoad;
    observationGroup: ObservationPrimitiveGroup | null;
    observations: ObservationArtifact | null;
    progress?: SceneProgressListener;
    signal: AbortSignal;
    style: ScientificStyle;
    surface: SurfaceArtifact;
  }): Promise<void> {
    const {
      group,
      load,
      observationGroup,
      observations,
      progress,
      signal,
      style,
      surface,
    } = input;
    const displayed = this.#displayed;
    // A recolour streams no anchors (the worker rebuilds each chunk from its cached topology,
    // chunk plan and vertex means and sends none), so it is taken only when the displayed
    // group's marker heights exist to copy onto the new group; otherwise (no heights, e.g. after
    // removeSurface) a full build brings the anchors back. An artifact without observations has
    // no markers and needs no heights.
    const sourceHeights = displayed?.group
      ? this.#heights.get(displayed.group)
      : undefined;
    const recolour =
      (sourceHeights !== undefined || observations === null) &&
      displayed?.artifactKey === load.artifactKey &&
      displayed.metric === style.metric &&
      displayed.geometry === style.geometry &&
      displayed.palette !== style.palette;
    if (recolour) {
      if (sourceHeights) this.#heights.set(group, sourceHeights);
      group.setElevationFactor(this.#options.style().elevationFactor, true);
    }
    const request: BuildChunksBody = {
      artifactKey: load.artifactKey,
      geometry: style.geometry,
      gridSha256: surface.grid.gridSha256,
      lookAt: load.lookAt ?? this.#lookAt(),
      metric: style.metric,
      observationPoints: observationPoints(observations),
      palette: style.palette,
    };
    const queue = createMessageQueue<ChunkMessage>();
    const worker = this.#options.worker;
    const onChunk = (message: ChunkMessage) => queue.push(message);
    const producer = (
      recolour
        ? worker.recolour(request, onChunk, signal)
        : worker.buildChunks(request, onChunk, signal)
    ).then(
      () => queue.end(),
      (error: unknown) => queue.fail(error),
    );
    const sharedObservations =
      observationGroup !== null &&
      observationGroup === displayed?.observationGroup;
    let added = 0;
    progress?.({ detail: 'Building surface geometry', progress: null });
    const stats = await scheduleChunks(this.#options.scene, group, queue, {
      frameBudgetMs: this.#options.frameBudgetMs,
      onAdded: (message) => {
        added += 1;
        this.#perf.mark('atlas:chunk-add', {
          detail: { artifactKey: load.artifactKey, chunk: message.chunk },
        });
        progress?.({
          detail: 'Preparing surface geometry',
          progress:
            message.total > 0 ? Math.min(1, added / message.total) : null,
        });
      },
      onBeforeAdd: (message) => {
        if (!observations) {
          // No markers to anchor, so nothing waits on anchors: raise the group before its first
          // chunk is added (§B.6.8) rather than at the commit.
          if (added === 0)
            group.setElevationFactor(
              this.#options.style().elevationFactor,
              true,
            );
          return;
        }
        if (!message.anchors) return;
        const heights = observationHeightsFromBuffers(
          message.anchors,
          observations.observations,
          columnarHeightSource(surface),
          style.metric,
        );
        this.#heights.set(group, heights);
        if (observationGroup && !sharedObservations)
          observationGroup.setSurfaceHeights(heights);
        group.setElevationFactor(this.#options.style().elevationFactor, true);
      },
      order: [],
      signal,
    });
    await producer;
    this.#options.marks.setAttribute(REVEAL_ATTRIBUTE, JSON.stringify(stats));
  }

  async #commit(input: {
    cold: boolean;
    group: SurfaceChunkGroup;
    load: ArtifactLoad;
    observationGroup: ObservationPrimitiveGroup | null;
    observations: ObservationArtifact | null;
    progress?: SceneProgressListener;
    surface: SurfaceArtifact;
  }): Promise<void> {
    const {
      cold,
      group,
      load,
      observationGroup,
      observations,
      progress,
      surface,
    } = input;
    const style = this.#options.style();
    const outgoing = this.#displayed;
    const factor = style.elevationFactor;
    group.setElevationFactor(factor, true);
    group.setSurfaceOpacity(style.surfaceOpacity);
    group.setVisibility(style.layers.surface, style.layers.support);
    void group.setCellEdges(style.cellEdges);
    void group.setSceneMode(style.mode);
    if (observationGroup) {
      const presentation = style.observationStyle;
      observationGroup.setSurfaceHeights(this.#heights.get(group) ?? null);
      observationGroup.setElevationFactor(factor, true);
      observationGroup.setSizeRange(presentation.sizeRange);
      observationGroup.setSamplingAreaColor(presentation.samplingAreaColor);
      observationGroup.setStyleOpacity(presentation.opacity);
      observationGroup.setEarthOpacity(style.earthOpacity);
      observationGroup.setVisibility(
        style.layers.observations,
        presentation.samplingAreas,
      );
    }
    this.#displayed = {
      artifactId: load.artifactId,
      artifactKey: load.artifactKey,
      geometry: style.geometry,
      group,
      metric: style.metric,
      observationGroup,
      observations,
      palette: style.palette,
      surface,
    };
    this.#revealing = null;
    this.#options.highlight.setArtifacts(
      columnarHeightSource(surface),
      observations,
      style.metric,
      factor > 0,
      factor,
    );
    this.#syncDisplayedMarks(group, style);
    this.#raiseOverlays(observationGroup);
    this.#options.onCommit(load.artifactKey);
    if (!cold) {
      const incoming = fadeTogether(
        group !== outgoing?.group ? group : null,
        observationGroup !== outgoing?.observationGroup
          ? observationGroup
          : null,
      );
      const leaving = fadeTogether(
        outgoing?.group && outgoing.group !== group ? outgoing.group : null,
        outgoing?.observationGroup &&
          outgoing.observationGroup !== observationGroup
          ? outgoing.observationGroup
          : null,
      );
      if (incoming)
        await animateSwap(
          { scene: this.#options.scene },
          incoming,
          leaving,
          style.reducedMotion,
          true,
          (value) =>
            progress?.({ detail: 'Blending the new surface', progress: value }),
        );
      else if (leaving) {
        leaving.setOpacity(0);
        leaving.collection.show = false;
      }
    }
    if (this.#displayed?.group === group) group.setOpacity(1);
    if (
      observationGroup &&
      this.#displayed?.observationGroup === observationGroup
    )
      observationGroup.setOpacity(1);
    this.#prune();
    this.#options.scene.requestRender();
  }

  #syncDisplayedMarks(group: SurfaceChunkGroup, style: ScientificStyle): void {
    const marks = this.#options.marks;
    marks.clear('values-ready');
    if (this.#valuesReady.has(group.artifactKey)) marks.queue('values-ready');
    marks.clear('edges-ready');
    if (
      style.cellEdges &&
      group.edges.isBuilt() &&
      this.#edgeStyles.get(group) === edgeStyleKey(style)
    )
      marks.queue('edges-ready');
  }

  #startEdges(): void {
    const displayed = this.#displayed;
    const group = displayed?.group;
    if (!displayed || !group || !this.#options.style().cellEdges) return;
    void this.#buildEdges(displayed, group);
  }

  async #buildEdges(
    displayed: Displayed,
    group: SurfaceChunkGroup,
  ): Promise<void> {
    const style = this.#options.style();
    const key = edgeStyleKey(style);
    if (group.edges.isBuilt() && this.#edgeStyles.get(group) === key) {
      if (this.#displayed?.group === group)
        this.#options.marks.queue('edges-ready');
      return;
    }
    if (group.edges.isBuilt()) group.edges.reset();
    this.#edgeBuild?.abort();
    const abort = new AbortController();
    this.#edgeBuild = abort;
    try {
      await group.edges.build(
        (onChunk, signal) =>
          this.#options.worker.buildEdges(
            {
              artifactKey: displayed.artifactKey,
              edgeColor:
                style.edgeColorMode === 'matched'
                  ? { mode: 'matched' }
                  : { color: style.edgeFixedColor, mode: 'fixed' },
              // positions at exaggeration 1; the edge layer scales them linearly to the factor.
              factor: 1,
              geometry: displayed.geometry,
              gridSha256: displayed.surface.grid.gridSha256,
              lookAt: this.#lookAt(),
              metric: displayed.metric,
              palette: displayed.palette,
            },
            onChunk,
            signal,
          ),
        style.edgeFixedColor,
        style.mode,
        style.elevationFactor,
        abort.signal,
      );
      this.#edgeStyles.set(group, key);
      await group.setCellEdges(this.#options.style().cellEdges);
      if (this.#displayed?.group === group)
        this.#options.marks.queue('edges-ready');
    } catch (error) {
      if (!isAbortError(error))
        console.warn('Cell outlines could not be built.', error);
    }
  }

  #discard(epoch: Epoch, partial: SurfaceChunkGroup | null): void {
    const newer = this.#epoch === epoch ? null : this.#epoch;
    const displayed = this.#displayed;
    const keep = (group: object | null) =>
      group !== null &&
      (group === displayed?.group ||
        group === displayed?.observationGroup ||
        group === newer?.group ||
        group === newer?.observationGroup);
    if (partial && !keep(partial)) this.#dispose(partial);
    else if (epoch.group && !keep(epoch.group)) {
      epoch.group.setOpacity(0);
      epoch.group.collection.show = false;
    }
    if (epoch.observationGroup && !keep(epoch.observationGroup)) {
      epoch.observationGroup.setOpacity(0);
      epoch.observationGroup.collection.show = false;
    }
    if (this.#epoch === epoch) this.#epoch = null;
    // Superseded or failed, this epoch's reveal is no longer what picks resolve against.
    if (this.#revealing?.epoch === epoch) this.#revealing = null;
    this.#options.scene.requestRender();
  }

  #dispose(group: SurfaceChunkGroup | ObservationPrimitiveGroup): void {
    this.#ids.delete(group);
    this.#options.scene.primitives.remove(group.collection);
  }

  #prune(): void {
    const displayed = this.#displayed;
    if (displayed?.group)
      this.#surfaces.prune(displayed.group, (group) => this.#dispose(group));
    if (displayed?.observationGroup)
      this.#observations.prune(displayed.observationGroup, (group) =>
        this.#dispose(group),
      );
  }

  #raiseOverlays(observationGroup: ObservationPrimitiveGroup | null): void {
    raiseScientificOverlays(
      this.#options.scene.primitives,
      (observationGroup ?? this.#displayed?.observationGroup)?.collection ??
        null,
      this.#options.highlight.collection,
    );
  }

  #lookAt(): { lat: number; lon: number } {
    const { camera, canvas } = this.#options.scene;
    const hit = camera.pickEllipsoid(
      new Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2),
      Ellipsoid.WGS84,
    );
    const point =
      (hit ? Ellipsoid.WGS84.cartesianToCartographic(hit) : undefined) ??
      camera.positionCartographic;
    return {
      lat: CesiumMath.toDegrees(point.latitude),
      lon: CesiumMath.toDegrees(point.longitude),
    };
  }
}
