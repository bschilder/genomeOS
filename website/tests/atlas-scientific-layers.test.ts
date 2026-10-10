import { cellToLatLng } from 'h3-js';
import {
  Cartographic,
  Ellipsoid,
  Primitive,
  PrimitiveCollection,
  type Color,
  type PointPrimitiveCollection,
  type PolylineCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ObservationArtifact } from '../src/atlas/contracts';
import { LayerCache } from '../src/atlas/scene/layer-cache';
import { createMarkTracker } from '../src/atlas/scene/scene-marks';
import {
  DEFAULT_LAYERS,
  DEFAULT_OBSERVATIONS,
} from '../src/atlas/scene/scene-policy';
import {
  ScientificLayers,
  type ScientificStyle,
} from '../src/atlas/scene/scientific-layers';
import type {
  ArtifactLoad,
  AtlasMark,
  ObservationPresentation,
} from '../src/atlas/scene/types';
import type { SurfaceArtifact } from '../src/atlas/surface-columns';
import type {
  BuildChunksBody,
  ChunkMessage,
} from '../src/atlas/worker/protocol';
import type { ObservationPrimitiveGroup } from '../src/atlas/scene/observation-layer';
import type { SurfaceChunkGroup } from '../src/atlas/scene/surface-chunk-layer';
import { chunkMessage } from './helpers/chunk-buffers';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';
import { columnarSurface } from './helpers/columnar-surface';
import { FakeEvent, flushTasks } from './helpers/scene-fakes';

// Every group the layers build, so a test can read the opacity the swap gives each one. The
// wrappers pass straight through to the real factories.
const built = vi.hoisted(() => ({
  observations: [] as ObservationPrimitiveGroup[],
  surfaces: [] as SurfaceChunkGroup[],
}));
vi.mock('../src/atlas/scene/observation-layer', async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import('../src/atlas/scene/observation-layer')
    >();
  return {
    ...actual,
    buildObservationLayer: (
      ...args: Parameters<typeof actual.buildObservationLayer>
    ) => {
      const group = actual.buildObservationLayer(...args);
      built.observations.push(group);
      return group;
    },
  };
});
vi.mock('../src/atlas/scene/surface-chunk-layer', async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import('../src/atlas/scene/surface-chunk-layer')
    >();
  return {
    ...actual,
    createSurfaceChunkGroup: (
      ...args: Parameters<typeof actual.createSurfaceChunkGroup>
    ) => {
      const group = actual.createSurfaceChunkGroup(...args);
      built.surfaces.push(group);
      return group;
    },
  };
});

const CELL = '83754efffffffff';
const [LAT, LON] = cellToLatLng(CELL);
const SURFACE_CLEARANCE_METRES = 650;
const SYMBOL_CLEARANCE_METRES = 7_000;

function keyOf(id: string): string {
  return `${id}:v3:map-2026-08`;
}

function surfaceFor(id: string): SurfaceArtifact {
  return columnarSurface(
    [{ h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'observed' }],
    { id },
  );
}

function observationsFor(): ObservationArtifact {
  return {
    artifact: {},
    observations: [
      {
        ac: 25,
        an: 100,
        assay: 'genotype',
        citation_text: 'Example publication.',
        cohort_id: 'map-study-1',
        disease_ascertainment_excluded: true,
        ingest_version: 'map-2026-08',
        lat: LAT,
        lon: LON,
        population_label: 'Example population',
        radius_km: 12,
        sampling_design: 'population_random',
        source_locator: 'MAP survey 1',
        source_record_id: 'map-surveys:1',
        source_url: 'https://example.org/source',
        study_id: 'map-study-1',
        study_label: 'Example study',
      },
    ],
  } as unknown as ObservationArtifact;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, reject, resolve };
}

function markReady(collection: PrimitiveCollection): void {
  for (let index = 0; index < collection.length; index += 1) {
    const child: unknown = collection.get(index);
    if (child instanceof PrimitiveCollection) markReady(child);
    else if (child instanceof Primitive)
      (child as unknown as { _ready: boolean })._ready = true;
  }
}

function harness(overrides: Partial<ScientificStyle> = {}) {
  stubCesiumBrowserImageTypes();
  const preUpdate = new FakeEvent();
  const postRender = new FakeEvent();
  const primitives = new PrimitiveCollection();
  const scene = {
    camera: {
      pickEllipsoid: () => undefined,
      positionCartographic: Cartographic.fromDegrees(20, 12, 16_500_000),
    },
    canvas: { clientHeight: 600, clientWidth: 800 },
    postRender,
    preUpdate,
    primitives,
    requestRender: vi.fn(),
  };
  const attributes = new Map<string, string>();
  const marks = createMarkTracker(
    scene,
    { setAttribute: (name, value) => attributes.set(name, value) },
    { mark: vi.fn() },
  );
  const emitted: AtlasMark[] = [];
  marks.onMark((mark) => emitted.push(mark));
  const commits: string[] = [];
  const requests: BuildChunksBody[] = [];
  const highlight = {
    collection: new PrimitiveCollection(),
    setArtifacts: vi.fn(),
  };
  primitives.add(highlight.collection);
  const style: ScientificStyle = {
    cellEdges: false,
    earthOpacity: 1,
    edgeColorMode: 'matched',
    edgeFixedColor: '#b9f5ff',
    elevationFactor: 0,
    geometry: 'triangles',
    layers: { ...DEFAULT_LAYERS },
    metric: 'post_mean',
    mode: 'globe',
    observationStyle: { ...DEFAULT_OBSERVATIONS, shape: 'circle' },
    palette: 'rainbow',
    reducedMotion: true,
    surfaceOpacity: 0.58,
    ...overrides,
  };
  const stream = async (
    request: BuildChunksBody,
    onChunk: (message: ChunkMessage) => void,
    signal?: AbortSignal,
  ) => {
    requests.push(request);
    for (const chunk of [0, 1]) {
      await flushTasks();
      if (signal?.aborted) throw new DOMException('cancelled', 'AbortError');
      onChunk(
        chunkMessage(request.artifactKey, chunk, {
          anchors:
            chunk === 0 && request.observationPoints
              ? {
                  // Metric-dependent, so a test can tell which metric's heights the markers use.
                  heights: Float64Array.of(
                    request.metric === 'post_sd' ? 3_000 : 1_000,
                  ),
                  triangles: new Float64Array(9).fill(Number.NaN),
                }
              : null,
          total: 2,
        }),
      );
    }
  };
  // The real AtlasWorkerClient.recolour has the worker rebuild each chunk from its cached
  // topology, chunk plan and vertex means, and sends no anchors (Task 52 (B3.13)); the fake
  // matches it, so recolour tests see what production sees.
  const recolourStream = (
    request: BuildChunksBody,
    onChunk: (message: ChunkMessage) => void,
    signal?: AbortSignal,
  ) => stream({ ...request, observationPoints: null }, onChunk, signal);
  const worker = {
    buildChunks: vi.fn(stream),
    buildEdges: vi.fn(async () => {}),
    recolour: vi.fn(recolourStream),
  };
  const layers = new ScientificLayers({
    frameBudgetMs: 8,
    highlight,
    marks,
    onCommit: (key) => commits.push(key),
    perf: { mark: vi.fn() },
    scene: scene as never,
    style: () => style,
    worker: worker as never,
  });
  const frame = () => {
    preUpdate.raiseEvent();
    markReady(primitives);
    postRender.raiseEvent();
  };
  const pump = async (frames = 12) => {
    for (let index = 0; index < frames; index += 1) {
      await flushTasks();
      frame();
    }
  };
  const load = (
    id: string,
    surface: Promise<SurfaceArtifact> = Promise.resolve(surfaceFor(id)),
  ): ArtifactLoad => ({
    artifactId: id,
    artifactKey: keyOf(id),
    observations: Promise.resolve(observationsFor()),
    surface,
  });
  const show = async (id: string) => {
    const done = layers.setArtifact(load(id));
    await pump();
    await done;
    await pump(1);
  };
  const childCollections = () =>
    Array.from(
      { length: primitives.length },
      (_, index) => primitives.get(index) as PrimitiveCollection,
    );
  return {
    attributes,
    childCollections,
    commits,
    emitted,
    frame,
    highlight,
    layers,
    load,
    primitives,
    pump,
    requests,
    show,
    style,
    worker,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  built.observations.length = 0;
  built.surfaces.length = 0;
});

describe('cold progressive reveal', () => {
  it('shows observations first, then chunks with their masks, and commits once complete', async () => {
    const h = harness();
    const surface = deferred<SurfaceArtifact>();
    const done = h.layers.setArtifact(h.load('hbs-rs334', surface.promise));

    await flushTasks();
    h.frame();
    expect(h.emitted).toEqual(['observations-visible']);
    expect(h.attributes.get('data-atlas-displayed')).toBe('hbs-rs334');
    expect(h.commits).toEqual([]);

    surface.resolve(surfaceFor('hbs-rs334'));
    await h.pump();
    await done;
    await h.pump(1);

    expect(h.commits).toEqual([keyOf('hbs-rs334')]);
    expect(h.emitted).toEqual([
      'observations-visible',
      'surface-first-chunk',
      'surface-visible',
      'ready',
    ]);
    expect(h.attributes.get('data-atlas-surface-visible')).toBe('true');
    expect(JSON.parse(h.attributes.get('data-atlas-reveal')!)).toMatchObject({
      frames: expect.any(Number),
      longestFrameMs: expect.any(Number),
      totalMs: expect.any(Number),
    });
    expect(h.layers.displayedLayer()).toEqual({
      artifactKey: keyOf('hbs-rs334'),
      geometry: 'triangles',
      metric: 'post_mean',
      palette: 'rainbow',
    });
    expect(h.requests[0].observationPoints).toEqual(Float64Array.of(LON, LAT));
    expect(h.requests[0].lookAt.lat).toBeCloseTo(12);
    expect(h.requests[0].lookAt.lon).toBeCloseTo(20);
    expect(h.highlight.setArtifacts).toHaveBeenCalledTimes(1);
  });

  it('applies worker anchors before the first chunk is added at elevation', async () => {
    const h = harness({ elevationFactor: 2 });
    const done = h.layers.setArtifact(h.load('hbs-rs334'));
    let checked = false;
    for (let index = 0; index < 12 && !checked; index += 1) {
      await flushTasks();
      h.frame();
      const chunkGroup = h
        .childCollections()
        .find((child) => child.length === 3);
      const observations = h
        .childCollections()
        .find((child) => child.length === 5);
      if (chunkGroup && (chunkGroup.get(0) as PrimitiveCollection).length > 0) {
        const points = observations!.get(2) as PointPrimitiveCollection;
        expect(
          Ellipsoid.WGS84.cartesianToCartographic(points.get(0).position)
            .height,
        ).toBeCloseTo(
          SURFACE_CLEARANCE_METRES + 1_000 * 2 + SYMBOL_CLEARANCE_METRES,
          3,
        );
        checked = true;
      }
    }
    await h.pump();
    await done;
    expect(checked).toBe(true);
  });

  it('raises chunks during a cold reveal of an artifact without observations', async () => {
    // No markers means no anchors to wait for (§B.6.8): the group is raised before its first
    // chunk is added, and an elevation change during the reveal applies, instead of the surface
    // lying flat until the commit.
    const h = harness({ elevationFactor: 2 });
    const done = h.layers.setArtifact({
      ...h.load('hbs-rs334'),
      observations: Promise.resolve(null),
    });
    let checked = false;
    for (let index = 0; index < 12 && !checked; index += 1) {
      await flushTasks();
      h.frame();
      const chunkGroup = h
        .childCollections()
        .find((child) => child.length === 3);
      const surfaces = chunkGroup?.get(0) as PrimitiveCollection | undefined;
      if (surfaces && surfaces.length > 0 && h.commits.length === 0) {
        const factor = () =>
          (
            (surfaces.get(0) as Primitive).appearance as unknown as {
              uniforms: { u_elevationFactor: number };
            }
          ).uniforms.u_elevationFactor;
        expect(factor()).toBe(2);
        h.style.elevationFactor = 3;
        h.layers.setElevationFactor(3, true);
        expect(factor()).toBe(3);
        checked = true;
      }
    }
    await h.pump();
    await done;
    expect(checked).toBe(true);
  });

  it('renders nothing when the render tier fails during a cold load', async () => {
    const h = harness();
    const failing = deferred<SurfaceArtifact>();
    const outcome = h.layers
      .setArtifact(h.load('hbs-rs334', failing.promise))
      .catch((error: Error) => error);
    await flushTasks();
    h.frame();
    expect(h.attributes.get('data-atlas-displayed')).toBe('hbs-rs334');

    failing.reject(new Error('render tier failed its checksum'));
    await expect(outcome).resolves.toMatchObject({
      message: 'render tier failed its checksum',
    });
    h.frame();
    expect(h.attributes.get('data-atlas-displayed')).toBe('');
    expect(h.commits).toEqual([]);
  });

  it('stops picking a cold reveal once a newer request supersedes it', async () => {
    const h = harness();
    const first = h.layers.setArtifact(h.load('hbs-rs334'));
    for (let index = 0; index < 12 && !h.layers.pickTarget(); index += 1) {
      await flushTasks();
      h.frame();
    }
    expect(h.layers.pickTarget()).toMatchObject({
      artifactKey: keyOf('hbs-rs334'),
    });

    const observations = deferred<ObservationArtifact | null>();
    const surface = deferred<SurfaceArtifact>();
    const second = h.layers.setArtifact({
      ...h.load('g6pd-deficiency', surface.promise),
      observations: observations.promise,
    });
    await h.pump();
    await first;
    // The superseded reveal is gone and the newer request has no surface yet.
    expect(h.layers.pickTarget()).toBeNull();

    observations.resolve(null);
    surface.resolve(surfaceFor('g6pd-deficiency'));
    await h.pump();
    await second;
    expect(h.layers.pickTarget()).toMatchObject({
      artifactKey: keyOf('g6pd-deficiency'),
    });
  });
});

describe('atomic replacement', () => {
  it('builds a replacement hidden and swaps it in with one commit', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    const pending = deferred<SurfaceArtifact>();
    const second = h.layers.setArtifact(
      h.load('g6pd-deficiency', pending.promise),
    );

    await h.pump(3);
    expect(h.attributes.get('data-atlas-displayed')).toBe('hbs-rs334');
    pending.resolve(surfaceFor('g6pd-deficiency'));
    await flushTasks();
    h.frame();
    expect(h.attributes.get('data-atlas-displayed')).toBe('hbs-rs334');
    expect(h.layers.pickTarget()).toMatchObject({
      artifactKey: keyOf('hbs-rs334'),
    });
    // The incoming surface and observation groups (fix round 1, finding 1).
    expect(h.layers.pickTarget()!.hidden).toHaveLength(2);
    expect(h.commits).toEqual([keyOf('hbs-rs334')]);

    await h.pump();
    await second;
    await h.pump(1);
    expect(h.commits).toEqual([keyOf('hbs-rs334'), keyOf('g6pd-deficiency')]);
    expect(h.attributes.get('data-atlas-displayed')).toBe('g6pd-deficiency');
    expect(h.layers.displayedLayer()?.artifactKey).toBe(
      keyOf('g6pd-deficiency'),
    );
  });

  it('keeps the incoming observation group out of depth picks until the swap commits', async () => {
    // Translucent depth picks write depth whatever the alpha, so the opacity-0 incoming markers
    // and sampling-area rings would otherwise set the depth (§B.6.6).
    const h = harness();
    await h.show('hbs-rs334');
    const displayed = h.childCollections().find((child) => child.length === 5);
    const pending = deferred<SurfaceArtifact>();
    const second = h.layers.setArtifact(
      h.load('g6pd-deficiency', pending.promise),
    );
    await h.pump(3);
    const incoming = h
      .childCollections()
      .find((child) => child.length === 5 && child !== displayed);
    expect(incoming).toBeDefined();
    expect(h.layers.pickTarget()!.hidden).toEqual([incoming]);

    pending.resolve(surfaceFor('g6pd-deficiency'));
    await flushTasks();
    h.frame();
    expect(h.layers.pickTarget()!.hidden).toContain(incoming);
    expect(h.layers.pickTarget()!.hidden).not.toContain(displayed);

    await h.pump();
    await second;
    expect(h.layers.pickTarget()).toMatchObject({
      artifactKey: keyOf('g6pd-deficiency'),
      hidden: [],
    });
  });

  it('rebuilds a pending replacement, not the displayed artifact, on a style change', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    const pending = deferred<SurfaceArtifact>();
    const second = h.layers.setArtifact(
      h.load('g6pd-deficiency', pending.promise),
    );
    await h.pump(2);

    h.style.metric = 'post_sd';
    const rebuilt = h.layers.rebuild();
    pending.resolve(surfaceFor('g6pd-deficiency'));
    await h.pump();
    await Promise.all([second, rebuilt]);
    await h.pump(1);
    expect(h.commits).toEqual([keyOf('hbs-rs334'), keyOf('g6pd-deficiency')]);
    expect(h.layers.displayedLayer()).toMatchObject({
      artifactKey: keyOf('g6pd-deficiency'),
      metric: 'post_sd',
    });
    expect(h.attributes.get('data-atlas-displayed')).toBe('g6pd-deficiency');
  });

  it('rebuilds the displayed artifact once its replacement has failed', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    const failing = deferred<SurfaceArtifact>();
    const outcome = h.layers
      .setArtifact(h.load('g6pd-deficiency', failing.promise))
      .catch((error: Error) => error);
    failing.reject(new Error('render tier failed its checksum'));
    await expect(outcome).resolves.toMatchObject({
      message: 'render tier failed its checksum',
    });

    h.style.metric = 'post_sd';
    const rebuilt = h.layers.rebuild();
    await h.pump();
    await rebuilt;
    expect(h.commits).toEqual([keyOf('hbs-rs334'), keyOf('hbs-rs334')]);
    expect(h.layers.displayedLayer()).toMatchObject({
      artifactKey: keyOf('hbs-rs334'),
      metric: 'post_sd',
    });
  });

  it('restyles the incoming measured points during a replacement', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    const displayed = h.childCollections().find((child) => child.length === 5)!;
    const displayedAlpha = (displayed.get(2) as PointPrimitiveCollection).get(0)
      .color.alpha;
    const pending = deferred<SurfaceArtifact>();
    const second = h.layers.setArtifact(
      h.load('g6pd-deficiency', pending.promise),
    );
    await h.pump(2);
    const incoming = h
      .childCollections()
      .find((child) => child.length === 5 && child !== displayed)!;
    const points = incoming.get(2) as PointPrimitiveCollection;
    const rings = incoming.get(0) as PolylineCollection;

    const observationStyle: ObservationPresentation = {
      ...h.style.observationStyle,
      opacity: 0.5,
      samplingAreaColor: '#ff0000',
      sizeRange: [40, 40],
    };
    h.style.observationStyle = observationStyle;
    h.layers.setObservationAppearance(observationStyle, h.style.layers);
    h.style.earthOpacity = 0.5;
    h.layers.setEarthOpacity(0.5);
    expect(points.get(0).pixelSize).toBe(40);

    pending.resolve(surfaceFor('g6pd-deficiency'));
    await h.pump();
    await second;
    expect(h.layers.displayedLayer()?.artifactKey).toBe(
      keyOf('g6pd-deficiency'),
    );
    expect(points.get(0).color.alpha).toBeCloseTo(displayedAlpha * 0.25, 6);
    const ringColor = rings.get(0).material.uniforms.color as Color;
    expect(ringColor.red).toBe(1);
    expect(ringColor.green).toBe(0);
    expect(ringColor.alpha).toBeCloseTo(0.9 * 0.25, 6);
  });

  it('applies the observation style current at the commit to the incoming group', async () => {
    // As the commit does for the surface's opacity, visibility, outlines and mode.
    const h = harness();
    await h.show('hbs-rs334');
    const displayed = h.childCollections().find((child) => child.length === 5)!;
    const displayedAlpha = (displayed.get(2) as PointPrimitiveCollection).get(0)
      .color.alpha;
    const pending = deferred<SurfaceArtifact>();
    const second = h.layers.setArtifact(
      h.load('g6pd-deficiency', pending.promise),
    );
    await h.pump(2);
    const incoming = h
      .childCollections()
      .find((child) => child.length === 5 && child !== displayed)!;
    const points = incoming.get(2) as PointPrimitiveCollection;
    const rings = incoming.get(0) as PolylineCollection;

    h.style.observationStyle = {
      ...h.style.observationStyle,
      opacity: 0.5,
      samplingAreaColor: '#ff0000',
      sizeRange: [40, 40],
    };
    h.style.earthOpacity = 0.5;
    pending.resolve(surfaceFor('g6pd-deficiency'));
    await h.pump();
    await second;
    expect(points.get(0).pixelSize).toBe(40);
    expect(points.get(0).color.alpha).toBeCloseTo(displayedAlpha * 0.25, 6);
    const ringColor = rings.get(0).material.uniforms.color as Color;
    expect(ringColor.red).toBe(1);
    expect(ringColor.alpha).toBeCloseTo(0.9 * 0.25, 6);
  });

  it('commits only the latest request when one is superseded', async () => {
    const h = harness();
    const slow = deferred<SurfaceArtifact>();
    const first = h.layers.setArtifact(h.load('hbs-rs334', slow.promise));
    const second = h.layers.setArtifact(h.load('g6pd-deficiency'));
    slow.resolve(surfaceFor('hbs-rs334'));

    await h.pump();
    await Promise.all([first, second]);
    await h.pump(1);
    expect(h.commits).toEqual([keyOf('g6pd-deficiency')]);
    expect(h.attributes.get('data-atlas-displayed')).toBe('g6pd-deficiency');
  });

  it('marks ready only for the request that is still current when its swap ends', async () => {
    // A request made during another's swap animation begins a new epoch; the older request's
    // `ready` must not land in it (ledger Task 58 ruling; spec §B.1 `atlas:ready`).
    const h = harness({ reducedMotion: false });
    const animationFrames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
      animationFrames.push(callback),
    );
    const readyCount = () =>
      h.emitted.filter((mark) => mark === 'ready').length;
    await h.show('hbs-rs334');
    expect(readyCount()).toBe(1);

    const second = h.layers.setArtifact(h.load('g6pd-deficiency'));
    await h.pump();
    expect(h.commits).toEqual([keyOf('hbs-rs334'), keyOf('g6pd-deficiency')]);
    expect(animationFrames).not.toHaveLength(0);
    const pending = deferred<SurfaceArtifact>();
    const third = h.layers.setArtifact(h.load('kir-3ds1', pending.promise));
    while (animationFrames.length > 0)
      animationFrames.shift()!(performance.now() + 1_000);
    await second;
    await h.pump(2);
    expect(readyCount()).toBe(1);

    pending.resolve(surfaceFor('kir-3ds1'));
    for (let index = 0; index < 4 && animationFrames.length === 0; index += 1)
      await h.pump();
    while (animationFrames.length > 0)
      animationFrames.shift()!(performance.now() + 1_000);
    await third;
    await h.pump(1);
    expect(h.commits.at(-1)).toBe(keyOf('kir-3ds1'));
    expect(readyCount()).toBe(2);
  });

  it('fades the incoming surface and observations together against the outgoing pair (animated swap)', async () => {
    // Spec §B.6.8: every replacement is one atomic swap. With motion on, each frame of the
    // 300 ms fade gives the incoming surface and its observations the same opacity p and the
    // outgoing pair 1 - p; reduced motion would hide a non-atomic swap (both jump to 1 at once).
    const h = harness({ reducedMotion: false });
    const animationFrames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
      animationFrames.push(callback),
    );
    await h.show('hbs-rs334');
    expect(built.surfaces).toHaveLength(1);
    expect(built.observations).toHaveLength(1);
    const [surfaceOut] = built.surfaces;
    const [pointsOut] = built.observations;

    const swap = h.layers.setArtifact(h.load('g6pd-deficiency'));
    for (let index = 0; index < 4 && animationFrames.length === 0; index += 1)
      await h.pump();
    expect(animationFrames).not.toHaveLength(0);
    const surfaceIn = built.surfaces.at(-1)!;
    const pointsIn = built.observations.at(-1)!;
    expect([surfaceIn, pointsIn]).not.toContain(surfaceOut);
    expect(pointsIn).not.toBe(pointsOut);
    // Built hidden: nothing of the replacement shows before the fade starts.
    expect([surfaceIn.opacity(), pointsIn.opacity()]).toEqual([0, 0]);

    animationFrames.shift()!(performance.now() + 150);
    const progress = surfaceIn.opacity();
    expect(progress).toBeGreaterThan(0);
    expect(progress).toBeLessThan(1);
    expect(pointsIn.opacity()).toBe(progress);
    expect(surfaceOut.opacity()).toBeCloseTo(1 - progress, 12);
    expect(pointsOut.opacity()).toBeCloseTo(1 - progress, 12);

    while (animationFrames.length > 0)
      animationFrames.shift()!(performance.now() + 1_000);
    await swap;
    expect([surfaceIn.opacity(), pointsIn.opacity()]).toEqual([1, 1]);
    expect([surfaceOut.opacity(), pointsOut.opacity()]).toEqual([0, 0]);
    expect(h.commits.at(-1)).toBe(keyOf('g6pd-deficiency'));
  });

  it('recolours a palette change in the worker and reuses cached groups', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    h.style.palette = 'viridis';
    const recoloured = h.layers.rebuild();
    await h.pump();
    await recoloured;
    expect(h.worker.recolour).toHaveBeenCalledTimes(1);
    expect(h.worker.buildChunks).toHaveBeenCalledTimes(1);

    h.style.palette = 'rainbow';
    const back = h.layers.rebuild();
    await h.pump();
    await back;
    expect(h.worker.buildChunks).toHaveBeenCalledTimes(1);
    expect(h.worker.recolour).toHaveBeenCalledTimes(1);
    expect(h.commits).toHaveLength(3);
  });

  it('keeps measured points raised through a palette-only recolour at elevation', async () => {
    const h = harness({ elevationFactor: 2 });
    const pointHeight = () => {
      const observations = h
        .childCollections()
        .find((child) => child.length === 5)!;
      const points = observations.get(2) as PointPrimitiveCollection;
      return Ellipsoid.WGS84.cartesianToCartographic(points.get(0).position)
        .height;
    };
    const raised = (anchor: number) =>
      SURFACE_CLEARANCE_METRES + anchor * 2 + SYMBOL_CLEARANCE_METRES;
    const rebuild = async () => {
      const done = h.layers.rebuild();
      await h.pump();
      await done;
      await h.pump(1);
    };
    await h.show('hbs-rs334');
    expect(pointHeight()).toBeCloseTo(raised(1_000), 3);

    // Palette only: the worker recolours (no anchors), the markers keep their heights.
    h.style.palette = 'viridis';
    await rebuild();
    expect(h.worker.recolour).toHaveBeenCalledTimes(1);
    expect(pointHeight()).toBeCloseTo(raised(1_000), 3);
    expect(pointHeight()).toBeGreaterThan(
      SURFACE_CLEARANCE_METRES + SYMBOL_CLEARANCE_METRES,
    );

    // Another metric builds with its own anchors.
    h.style.metric = 'post_sd';
    await rebuild();
    expect(h.worker.buildChunks).toHaveBeenCalledTimes(2);
    expect(pointHeight()).toBeCloseTo(raised(3_000), 3);

    // Back to post_mean with the recoloured palette: a cache hit on the recoloured group, whose
    // copied heights are post_mean's, not the other metric's.
    h.style.metric = 'post_mean';
    await rebuild();
    expect(h.worker.buildChunks).toHaveBeenCalledTimes(2);
    expect(pointHeight()).toBeCloseTo(raised(1_000), 3);
  });
});

describe('displayed-artifact state', () => {
  it('reports cell values ready only for the displayed artifact', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    h.layers.markValuesReady(keyOf('g6pd-deficiency'));
    h.frame();
    expect(h.attributes.get('data-atlas-values-ready')).toBe('false');
    h.layers.markValuesReady(keyOf('hbs-rs334'));
    h.frame();
    expect(h.attributes.get('data-atlas-values-ready')).toBe('true');

    await h.show('kir-3ds1');
    expect(h.attributes.get('data-atlas-values-ready')).toBe('false');
  });

  it('removes the displayed surface when its cell values fail validation', async () => {
    const h = harness();
    await h.show('hbs-rs334');
    const before = h.primitives.length;
    h.layers.removeSurface(keyOf('hbs-rs334'));
    h.frame();
    expect(h.primitives.length).toBe(before - 1);
    expect(h.layers.pickTarget()?.artifactKey).toBe(keyOf('hbs-rs334'));
    expect(h.attributes.get('data-atlas-displayed')).toBe('hbs-rs334');
  });

  it('forgets a group removed from the layer cache', () => {
    const cache = new LayerCache<object>(2);
    const value = {};
    cache.set('a', value);
    cache.delete(value);
    expect(cache.get('a')).toBeUndefined();
  });
});
