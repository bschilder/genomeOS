import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AtlasWorkerClient,
  AtlasWorkerError,
  isArtifactValidationError,
  startAtlasWorker,
  type StepTiming,
} from '../src/atlas/worker/client';
import { ATLAS_WORKER_HANDLERS } from '../src/atlas/worker/handlers';
import {
  goldenBytes,
  goldenCatalog,
  goldenSurfaceJson,
  onlyGrid,
  toBuffer,
} from './support/gosa-builder';
import { InProcessWorker } from './support/in-process-worker';

const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const ref = catalog.artifacts[0];

afterEach(() => {
  vi.unstubAllGlobals();
});

function client(worker = new InProcessWorker()) {
  return { client: new AtlasWorkerClient(worker.asWorker()), worker };
}

describe('AtlasWorkerClient', () => {
  it('transfers each tier to the worker and resolves the decoded columns', async () => {
    const { client: atlas } = client();
    const gridBuffer = toBuffer(goldenBytes(entry.url));
    const grid = await atlas.loadGrid(gridBuffer, { entry, gridSha256 });
    expect(gridBuffer.byteLength).toBe(0);
    expect(grid.n).toBe(entry.n_cells);
    const render = await atlas.loadRender(
      toBuffer(goldenBytes(ref.web.render.url)),
      ref,
    );
    const detail = await atlas.loadDetail(
      toBuffer(goldenBytes(ref.web.detail.url)),
      ref,
    );
    expect(render.post_mean.length).toBe(grid.n);
    expect(Array.from(detail.post_mean)).toEqual(
      goldenSurfaceJson(ref).cells.map(({ post_mean }) => post_mean),
    );
  });

  it('reports checksum failures as artifact validation errors', async () => {
    const { client: atlas } = client();
    await atlas.loadGrid(toBuffer(goldenBytes(entry.url)), {
      entry,
      gridSha256,
    });
    const flipped = goldenBytes(ref.web.render.url);
    flipped[0] ^= 0xff;
    const failure = atlas.loadRender(toBuffer(flipped), ref);
    await expect(failure).rejects.toBeInstanceOf(AtlasWorkerError);
    await expect(failure).rejects.toMatchObject({
      code: 'checksum',
      gosaCode: 'container_sha256',
    });
    expect(
      isArtifactValidationError(await failure.catch((error: unknown) => error)),
    ).toBe(true);
    expect(isArtifactValidationError(new Error('network'))).toBe(false);
  });

  it('refuses a detail tier whose render tier was never loaded', async () => {
    const { client: atlas } = client();
    await expect(
      atlas.loadDetail(toBuffer(goldenBytes(ref.web.detail.url)), ref),
    ).rejects.toThrow(`Load the ${ref.id} render tier before its detail tier`);
  });

  it('cancels a superseded request by id', async () => {
    const gate = Promise.withResolvers<void>();
    const worker = new InProcessWorker({
      ...ATLAS_WORKER_HANDLERS,
      'load-grid': async (_request, context) => {
        await gate.promise;
        context.signal.throwIfAborted();
      },
    });
    const { client: atlas } = client(worker);
    const controller = new AbortController();
    const request = atlas.loadGrid(
      toBuffer(goldenBytes(entry.url)),
      { entry, gridSha256 },
      controller.signal,
    );
    await Promise.resolve();
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    gate.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const [load, cancel] = worker.received;
    expect(cancel).toEqual({ id: load.id, type: 'cancel' });
  });

  it('rejects an already-aborted request without posting it', async () => {
    const { client: atlas, worker } = client();
    const controller = new AbortController();
    controller.abort();
    await expect(
      atlas.loadGrid(
        toBuffer(goldenBytes(entry.url)),
        { entry, gridSha256 },
        controller.signal,
      ),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(worker.received).toHaveLength(0);
  });

  it('converts worker step timings to the page clock and records measures', async () => {
    const { client: atlas } = client();
    const timings: StepTiming[] = [];
    const stop = atlas.onStepTiming((timing) => timings.push(timing));
    const before = performance.now();
    await atlas.loadGrid(toBuffer(goldenBytes(entry.url)), {
      entry,
      gridSha256,
    });
    stop();
    // The geometry handlers add a `topology` step after grid-ready; only the data steps are pinned here.
    const data = timings.filter(({ step }) => step !== 'topology');
    expect(data.map(({ step }) => step)).toEqual([
      'verify-grid',
      'decode-grid',
    ]);
    expect(
      data.every(
        ({ artifactKey, chunk }) => artifactKey === null && chunk === null,
      ),
    ).toBe(true);
    for (const timing of data) {
      expect(timing.start).toBeGreaterThanOrEqual(before - 1);
      expect(timing.end).toBeGreaterThanOrEqual(timing.start);
      expect(timing.end).toBeLessThanOrEqual(performance.now() + 1);
    }
    const measures = performance.getEntriesByName(
      'atlas:worker:decode-grid',
      'measure',
    );
    expect(measures.length).toBeGreaterThan(0);
    expect((measures.at(-1) as PerformanceMeasure).detail).toEqual({
      artifactKey: null,
      chunk: null,
      step: 'decode-grid',
    });
  });

  it('fails every pending request when the worker crashes', async () => {
    const worker = new InProcessWorker({
      ...ATLAS_WORKER_HANDLERS,
      'load-grid': () => new Promise<void>(() => undefined),
    });
    const { client: atlas } = client(worker);
    const request = atlas.loadGrid(toBuffer(goldenBytes(entry.url)), {
      entry,
      gridSha256,
    });
    await Promise.resolve();
    worker.crash('boom');
    await expect(request).rejects.toThrow('Atlas data worker failed: boom');
  });

  it('yields a failing client when the Worker cannot start', async () => {
    vi.stubGlobal(
      'Worker',
      class {
        constructor() {
          throw new Error('blocked by policy');
        }
      },
    );
    const atlas = startAtlasWorker();
    await expect(
      atlas.loadGrid(toBuffer(goldenBytes(entry.url)), { entry, gridSha256 }),
    ).rejects.toThrow(/could not start: blocked by policy/);
  });
});
