import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { atlasCatalogSchema } from '../src/atlas/contracts';
import { SUPPORT_CODES } from '../src/atlas/gosa/decode';
import type { DecodedGrid, DecodedRender } from '../src/atlas/gosa/types';
import { artifactKeyFor } from '../src/atlas/surface-columns';
import { AtlasWorkerClient } from '../src/atlas/worker/client';
import { orderChunksForCamera, planChunks } from '../src/atlas/geometry/chunks';
import {
  buildEdgeChunk,
  edgeCapacity,
} from '../src/atlas/geometry/edge-buffers';
import {
  naturalEarthHeights,
  parseNaturalEarth,
} from '../src/atlas/geometry/natural-earth';
import { buildSurfaceChunk } from '../src/atlas/geometry/surface-buffers';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import type {
  ChunkMessage,
  GeometryResponse,
} from '../src/atlas/worker/protocol';
import {
  createGeometryWorker,
  messageChannelYield,
  type GeometryWorkerContext,
} from '../src/atlas/worker/geometry-handlers';
import { PARITY_DIR, surfaceFixturesIn } from './helpers/atlas-geometry';
import {
  fixtureBytes,
  goldenBytes,
  goldenCatalog,
  onlyGrid,
  toBuffer,
} from './support/gosa-builder';
import { InProcessWorker } from './support/in-process-worker';

const ARTIFACT_KEY = 'cyt-il-6-174-c:v3:afnd-2026-08';
const LOOK_AT = { lat: 50, lon: 35 };

interface Posted {
  message: GeometryResponse;
  transfer: Transferable[];
}

function harness(cancelAfterChunks = Number.POSITIVE_INFINITY) {
  const [fixture] = surfaceFixturesIn(PARITY_DIR);
  const render: DecodedRender = {
    artifact: fixture.artifact,
    post_mean: fixture.post_mean,
    post_sd: fixture.post_sd,
    support: Uint8Array.from(fixture.cells, (cell) =>
      SUPPORT_CODES.indexOf(cell.support),
    ),
  };
  const posted: Posted[] = [];
  let clock = 0;
  const context: GeometryWorkerContext = {
    grid: (sha) => (sha === fixture.grid.gridSha256 ? fixture.grid : undefined),
    gridFor: (key) => (key === ARTIFACT_KEY ? fixture.grid : undefined),
    isCancelled: () =>
      posted.filter(({ message }) => message.type === 'chunk').length >=
      cancelAfterChunks,
    now: () => (clock += 1),
    post: (message, transfer) => posted.push({ message, transfer }),
    render: (key) => (key === ARTIFACT_KEY ? render : undefined),
    yieldToEventLoop: () => Promise.resolve(),
  };
  return {
    context,
    fixture,
    posted,
    render,
    worker: createGeometryWorker(context),
  };
}

function request(gridSha256: string) {
  return {
    artifactKey: ARTIFACT_KEY,
    geometry: 'triangles' as const,
    gridSha256,
    id: 7,
    lookAt: LOOK_AT,
    metric: 'post_sd' as const,
    observationPoints: Float64Array.from([36.8, 54.1, 0, 0]),
    palette: 'plasma' as const,
    type: 'build-chunks' as const,
  };
}

function ofType<T extends GeometryResponse['type']>(posted: Posted[], type: T) {
  return posted.filter((entry) => entry.message.type === type) as {
    message: Extract<GeometryResponse, { type: T }>;
    transfer: Transferable[];
  }[];
}

describe('geometry worker handlers (fast-load §B.6.3, §B.6.5)', () => {
  it('streams one transferable chunk per chunk in camera order, anchors first', async () => {
    const { fixture, posted, worker } = harness();
    await worker.handlers['build-chunks'](request(fixture.grid.gridSha256));
    const topology = buildGridTopology(fixture.grid);
    const plan = planChunks(fixture.grid, topology);
    const chunks = ofType(posted, 'chunk');
    expect(chunks.map(({ message }) => message.surface.chunk)).toEqual(
      orderChunksForCamera(plan, LOOK_AT),
    );
    expect(chunks.map(({ message }) => message.index)).toEqual(
      chunks.map((_, index) => index),
    );
    expect(chunks[0].message.anchors?.heights).toHaveLength(2);
    expect(
      chunks.slice(1).every(({ message }) => message.anchors === null),
    ).toBe(true);
    for (const { message, transfer } of chunks) {
      expect(new Set(transfer).size).toBe(transfer.length);
      expect(transfer).toContain(message.surface.positions.buffer);
      expect(transfer).toContain(message.surface.indices.buffer);
      if (message.support.unknown)
        expect(transfer).toContain(message.support.unknown.st.buffer);
    }
    expect(posted.at(-1)!.message).toEqual({
      artifactKey: ARTIFACT_KEY,
      id: 7,
      total: chunks.length,
      type: 'chunks-done',
    });
  });

  it('times topology once per grid and mesh and support per chunk', async () => {
    const { fixture, posted, worker } = harness();
    worker.warmGrid(1, fixture.grid.gridSha256);
    await worker.handlers['build-chunks'](request(fixture.grid.gridSha256));
    await worker.handlers['build-chunks']({
      ...request(fixture.grid.gridSha256),
      id: 8,
    });
    const timings = ofType(posted, 'step-timing').map(({ message }) => message);
    expect(timings.filter(({ step }) => step === 'topology')).toHaveLength(1);
    const chunks = ofType(posted, 'chunk').length;
    expect(timings.filter(({ step }) => step === 'mesh')).toHaveLength(chunks);
    expect(timings.filter(({ step }) => step === 'support')).toHaveLength(
      chunks,
    );
    expect(
      timings.every(
        ({ endEpochMs, startEpochMs }) => startEpochMs <= endEpochMs,
      ),
    ).toBe(true);
    expect(
      timings
        .filter(({ step }) => step === 'mesh')
        .every(
          ({ artifactKey, chunk }) =>
            artifactKey === ARTIFACT_KEY && chunk !== null,
        ),
    ).toBe(true);
  });

  it('stops at a cancelled request without finishing', async () => {
    const { fixture, posted, worker } = harness(2);
    await worker.handlers['build-chunks'](request(fixture.grid.gridSha256));
    expect(ofType(posted, 'chunk')).toHaveLength(2);
    expect(ofType(posted, 'chunks-done')).toHaveLength(0);
    expect(posted.at(-1)!.message).toMatchObject({
      code: 'cancelled',
      id: 7,
      type: 'error',
    });
  });

  it('recolours every chunk in plan order with fresh-build colours', async () => {
    const { fixture, posted, render, worker } = harness();
    await worker.handlers.recolour({
      artifactKey: ARTIFACT_KEY,
      geometry: 'hexagons',
      gridSha256: fixture.grid.gridSha256,
      id: 9,
      metric: 'post_mean',
      palette: 'viridis',
      type: 'recolour',
    });
    const topology = buildGridTopology(fixture.grid);
    const plan = planChunks(fixture.grid, topology);
    const chunks = ofType(posted, 'chunk').map(
      ({ message }) => message as ChunkMessage,
    );
    expect(chunks.map((message) => message.surface.chunk)).toEqual(
      plan.chunks.map((chunk) => chunk.id),
    );
    chunks.forEach((message) => {
      const fresh = buildSurfaceChunk(
        {
          domain: render.artifact.metric_domains.post_mean,
          geometry: 'hexagons',
          grid: fixture.grid,
          palette: 'viridis',
          support: render.support,
          topology,
          values: render.post_mean,
        },
        plan.chunks[message.surface.chunk],
      );
      expect(Array.from(message.surface.colors)).toEqual(
        Array.from(fresh.colors),
      );
      expect(message.anchors).toBeNull();
    });
  });

  it('sends exact edge capacities with every edge chunk', async () => {
    const { fixture, posted, render, worker } = harness();
    await worker.handlers['build-edges']({
      artifactKey: ARTIFACT_KEY,
      edgeColor: { mode: 'matched' },
      factor: 0,
      geometry: 'triangles',
      gridSha256: fixture.grid.gridSha256,
      id: 11,
      lookAt: LOOK_AT,
      metric: 'post_mean',
      palette: 'rainbow',
      type: 'build-edges',
    });
    const topology = buildGridTopology(fixture.grid);
    const plan = planChunks(fixture.grid, topology);
    const expected = edgeCapacity(
      plan.chunks.map((chunk) =>
        buildEdgeChunk(
          {
            domain: render.artifact.metric_domains.post_mean,
            geometry: 'triangles',
            grid: fixture.grid,
            palette: 'rainbow',
            support: render.support,
            topology,
            values: render.post_mean,
          },
          chunk,
          { mode: 'matched' },
        ),
      ),
    );
    const edges = ofType(posted, 'edges-chunk');
    expect(edges).toHaveLength(plan.chunks.length);
    for (const { message } of edges) expect(message).toMatchObject(expected);
    expect(posted.at(-1)!.message.type).toBe('edges-done');
  });

  it('parses Natural Earth and later returns its surface heights', async () => {
    const { fixture, posted, render, worker } = harness();
    const geojson = {
      features: [
        {
          geometry: {
            coordinates: [
              [
                [36.8, 54.1],
                [37.5, 54.1],
                [37.5, 55],
                [36.8, 54.1],
              ],
            ],
            type: 'Polygon',
          },
          properties: { LABEL_X: 37, LABEL_Y: 54.5, NAME_LONG: 'Fixture' },
          type: 'Feature',
        },
      ],
      type: 'FeatureCollection',
    };
    const json = new TextEncoder().encode(JSON.stringify(geojson))
      .buffer as ArrayBuffer;
    await worker.handlers['parse-context']({
      id: 12,
      json,
      type: 'parse-context',
    });
    const [ready] = ofType(posted, 'context-ready');
    expect(ready.message.buffers).toEqual(parseNaturalEarth(geojson));
    await worker.handlers['context-heights']({
      artifactKey: ARTIFACT_KEY,
      id: 13,
      metric: 'post_mean',
      type: 'context-heights',
    });
    const [heights] = ofType(posted, 'context-heights-ready');
    expect(heights.message).toMatchObject(
      naturalEarthHeights(parseNaturalEarth(geojson), {
        domain: render.artifact.metric_domains.post_mean,
        grid: fixture.grid as DecodedGrid,
        support: render.support,
        values: render.post_mean,
      }),
    );
  });

  it('reports a missing render tier and a malformed context as errors', async () => {
    const { fixture, posted, worker } = harness();
    await worker.handlers['build-chunks']({
      ...request(fixture.grid.gridSha256),
      artifactKey: 'absent:v1:d1',
    });
    expect(posted.at(-1)!.message).toMatchObject({
      code: 'internal',
      id: 7,
      type: 'error',
    });
    await worker.handlers['parse-context']({
      id: 14,
      json: new TextEncoder().encode('{"type":"Feature"}')
        .buffer as ArrayBuffer,
      type: 'parse-context',
    });
    expect(posted.at(-1)!.message).toMatchObject({
      code: 'validation',
      id: 14,
      type: 'error',
    });
  });
});

describe('worker yield (fast-load §B.6.9)', () => {
  it('resolves each yield after already-queued microtasks, in order', async () => {
    const yieldToEventLoop = messageChannelYield();
    const order: string[] = [];
    const first = yieldToEventLoop().then(() => order.push('first'));
    const second = yieldToEventLoop().then(() => order.push('second'));
    await Promise.resolve().then(() => order.push('microtask'));
    await Promise.all([first, second]);
    expect(order).toEqual(['microtask', 'first', 'second']);
  });
});

describe('AtlasWorkerClient geometry requests through the dispatcher (fast-load §B.6.3)', () => {
  it('streams chunks, recolours and answers context heights for a loaded render tier', async () => {
    const catalog = goldenCatalog();
    const { entry, gridSha256 } = onlyGrid(catalog);
    const ref = catalog.artifacts[0];
    const client = new AtlasWorkerClient(new InProcessWorker().asWorker());
    await client.loadGrid(toBuffer(goldenBytes(entry.url)), {
      entry,
      gridSha256,
    });
    await client.loadRender(toBuffer(goldenBytes(ref.web.render.url)), ref);
    const body = {
      artifactKey: artifactKeyFor(ref),
      geometry: 'triangles' as const,
      gridSha256,
      lookAt: { lat: 0, lon: 0 },
      metric: 'post_mean' as const,
      observationPoints: null,
      palette: 'viridis' as const,
    };
    const built: ChunkMessage[] = [];
    await client.buildChunks(body, (message) => built.push(message));
    expect(built.length).toBeGreaterThan(0);
    expect(built.map(({ index }) => index)).toEqual(
      built.map((_, index) => index),
    );
    expect(built.every(({ chunk, surface }) => chunk === surface.chunk)).toBe(
      true,
    );
    expect(built.every(({ total }) => total === built.length)).toBe(true);

    const recoloured: ChunkMessage[] = [];
    await client.recolour({ ...body, palette: 'plasma' }, (message) =>
      recoloured.push(message),
    );
    expect(recoloured).toHaveLength(built.length);
    expect(recoloured.every(({ anchors }) => anchors === null)).toBe(true);

    const geojson = {
      features: [
        {
          geometry: {
            coordinates: [
              [
                [0, 0],
                [1, 0],
                [1, 1],
                [0, 0],
              ],
            ],
            type: 'Polygon',
          },
          properties: { LABEL_X: 0.5, LABEL_Y: 0.5, NAME_LONG: 'Fixture' },
          type: 'Feature',
        },
      ],
      type: 'FeatureCollection',
    };
    const parsed = await client.parseContext(
      new TextEncoder().encode(JSON.stringify(geojson)).buffer as ArrayBuffer,
    );
    expect(parsed.labels).toHaveLength(1);
    const heights = await client.contextHeights({
      artifactKey: body.artifactKey,
      metric: 'post_mean',
    });
    expect(heights.borderHeights).toHaveLength(parsed.lonLat.length / 2);
    expect(heights.labelHeights).toHaveLength(1);
    client.terminate();
  });

  it('builds chunks for the first of nine loaded render tiers (no worker-side eviction)', async () => {
    // A return to an earlier dataset reuses the provider's cached surface and sends no new
    // render tier, so the worker must still hold it (Task 31 (B2.8)'s state.ts).
    const e2e = path.resolve(import.meta.dirname, 'fixtures/atlas/e2e');
    const catalog = atlasCatalogSchema.parse(
      JSON.parse(readFileSync(path.join(e2e, 'catalog.json'), 'utf8')),
    );
    const { entry, gridSha256 } = onlyGrid(catalog);
    const refs = catalog.artifacts.slice(0, 9);
    const client = new AtlasWorkerClient(new InProcessWorker().asWorker());
    await client.loadGrid(toBuffer(fixtureBytes(e2e, entry.url)), {
      entry,
      gridSha256,
    });
    for (const artifact of refs)
      await client.loadRender(
        toBuffer(fixtureBytes(e2e, artifact.web.render.url)),
        artifact,
      );
    const built: ChunkMessage[] = [];
    await client.buildChunks(
      {
        artifactKey: artifactKeyFor(refs[0]),
        geometry: 'triangles',
        gridSha256,
        lookAt: { lat: 0, lon: 0 },
        metric: 'post_mean',
        observationPoints: null,
        palette: 'viridis',
      },
      (message) => built.push(message),
    );
    expect(built.length).toBeGreaterThan(0);
    client.terminate();
  });
});
