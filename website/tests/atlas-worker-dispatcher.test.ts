import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { atlasCatalogSchema } from '../src/atlas/contracts';
import { decodeGrid, decodeRender } from '../src/atlas/gosa/decode';
import { artifactKeyFor } from '../src/atlas/surface-columns';
import {
  createDispatcher,
  type HandlerRegistry,
} from '../src/atlas/worker/dispatcher';
import { ATLAS_WORKER_HANDLERS } from '../src/atlas/worker/handlers';
import type {
  StepTimingMessage,
  WorkerInbound,
  WorkerOutbound,
} from '../src/atlas/worker/protocol';
import { createWorkerState } from '../src/atlas/worker/state';
import {
  fixtureBytes,
  goldenBytes,
  goldenCatalog,
  onlyGrid,
  refWith,
  toBuffer,
} from './support/gosa-builder';

const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const ref = catalog.artifacts[0];

function harness(handlers: HandlerRegistry = ATLAS_WORKER_HANDLERS) {
  const sent: { message: WorkerOutbound; transfer: Transferable[] }[] = [];
  const state = createWorkerState();
  const dispatch = createDispatcher(
    { post: (message, transfer) => sent.push({ message, transfer }) },
    handlers,
    state,
  );
  return { dispatch, sent, state };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function terminal(sent: { message: WorkerOutbound }[], id: number) {
  return sent
    .map(({ message }) => message)
    .find((message) => message.id === id && message.type !== 'step-timing');
}

function loadGrid(id = 1): WorkerInbound {
  return {
    buf: toBuffer(goldenBytes(entry.url)),
    expect: { entry, gridSha256 },
    id,
    type: 'load-grid',
  };
}

describe('Atlas worker dispatcher', () => {
  it('decodes the grid, caches it and transfers a copy with step timings', async () => {
    const { dispatch, sent, state } = harness();
    const before = Date.now();
    dispatch(loadGrid());
    await settle();
    const ready = terminal(sent, 1);
    expect(ready?.type).toBe('grid-ready');
    if (ready?.type !== 'grid-ready') return;
    const expected = decodeGrid(toBuffer(goldenBytes(entry.url)), {
      entry,
      gridSha256,
    });
    expect(Array.from(ready.grid.h3Lo)).toEqual(Array.from(expected.h3Lo));
    expect(state.grids.get(gridSha256)?.h3Lo).not.toBe(ready.grid.h3Lo);
    const transfer = sent.find(({ message }) => message === ready)!.transfer;
    expect(transfer).toEqual([ready.grid.h3Lo.buffer, ready.grid.h3Hi.buffer]);
    // The geometry handlers warm the grid topology right after grid-ready; that is not a data step.
    const steps = sent
      .map(({ message }) => message)
      // A type predicate: without it the filtered array stays WorkerOutbound[] and
      // `.step`, `.artifactKey`, `.chunk` are TS2339.
      .filter(
        (message): message is StepTimingMessage =>
          message.type === 'step-timing' && message.step !== 'topology',
      );
    expect(steps.map((message) => message.step)).toEqual([
      'verify-grid',
      'decode-grid',
    ]);
    expect(steps.map(({ artifactKey, chunk }) => [artifactKey, chunk])).toEqual(
      [
        [null, null],
        [null, null],
      ],
    );
    for (const step of steps) {
      // timeOrigin + now() and Date.now() are both epoch clocks but may drift by a few ms.
      expect(step.endEpochMs).toBeGreaterThanOrEqual(step.startEpochMs);
      expect(step.startEpochMs).toBeGreaterThanOrEqual(before - 1_000);
      expect(step.endEpochMs).toBeLessThanOrEqual(Date.now() + 1_000);
    }
  });

  it('refuses a render tier before its grid', async () => {
    const { dispatch, sent } = harness();
    dispatch({
      buf: toBuffer(goldenBytes(ref.web.render.url)),
      id: 2,
      ref,
      type: 'load-render',
    });
    await settle();
    expect(terminal(sent, 2)).toMatchObject({
      code: 'internal',
      gosaCode: null,
      type: 'error',
    });
  });

  it('decodes render and detail tiers and keeps the render resident by artifact key', async () => {
    const { dispatch, sent, state } = harness();
    dispatch(loadGrid());
    dispatch({
      buf: toBuffer(goldenBytes(ref.web.render.url)),
      id: 2,
      ref,
      type: 'load-render',
    });
    await settle();
    const rendered = terminal(sent, 2);
    expect(rendered?.type).toBe('render-ready');
    if (rendered?.type !== 'render-ready') return;
    rendered.render.support[0] = 9;
    expect(state.renders.get(artifactKeyFor(ref))?.support[0]).not.toBe(9);
    expect(state.renderGrids.get(artifactKeyFor(ref))).toBe(gridSha256);
    const grid = state.grids.get(gridSha256)!;
    const render = decodeRender(toBuffer(goldenBytes(ref.web.render.url)), {
      grid,
      ref,
    });
    dispatch({
      buf: toBuffer(goldenBytes(ref.web.detail.url)),
      id: 3,
      ref,
      render,
      type: 'load-detail',
    });
    await settle();
    expect(terminal(sent, 3)?.type).toBe('detail-ready');
    expect(
      sent
        .map(({ message }) => message)
        .filter(
          (message): message is StepTimingMessage =>
            message.type === 'step-timing' && message.step !== 'topology',
        )
        .map((message) => message.step),
    ).toEqual([
      'verify-grid',
      'decode-grid',
      'verify-render',
      'decode-render',
      'verify-detail',
      'decode-detail',
    ]);
  });

  it('maps digest failures to checksum and structural failures to validation', async () => {
    const { dispatch, sent } = harness();
    dispatch(loadGrid());
    const flipped = goldenBytes(ref.web.render.url);
    flipped[flipped.length - 1] ^= 0xff;
    dispatch({ buf: toBuffer(flipped), id: 2, ref, type: 'load-render' });
    const reserved = goldenBytes(ref.web.render.url);
    new DataView(reserved.buffer).setUint16(6, 1, true);
    dispatch({
      buf: toBuffer(reserved),
      id: 3,
      ref: refWith(ref, 'render', reserved),
      type: 'load-render',
    });
    await settle();
    expect(terminal(sent, 2)).toMatchObject({
      code: 'checksum',
      gosaCode: 'container_sha256',
      type: 'error',
    });
    expect(terminal(sent, 3)).toMatchObject({
      code: 'validation',
      gosaCode: 'reserved',
      type: 'error',
    });
  });

  it('reports a cancelled request as cancelled', async () => {
    const gate = Promise.withResolvers<void>();
    const { dispatch, sent } = harness({
      ...ATLAS_WORKER_HANDLERS,
      'load-grid': async (_request, context) => {
        await gate.promise;
        context.signal.throwIfAborted();
      },
    });
    dispatch(loadGrid(7));
    dispatch({ id: 7, type: 'cancel' });
    gate.resolve();
    await settle();
    expect(terminal(sent, 7)).toMatchObject({
      code: 'cancelled',
      type: 'error',
    });
  });

  it('reports an unknown message type as internal', async () => {
    const { dispatch, sent } = harness();
    dispatch({ id: 9, type: 'unknown' } as unknown as WorkerInbound);
    await settle();
    expect(terminal(sent, 9)).toMatchObject({
      code: 'internal',
      type: 'error',
    });
  });
});

describe('worker-resident render tiers', () => {
  it('keeps every decoded render tier the main thread can still hand out', async () => {
    // The provider caches every surface it returns and never re-sends a render tier on a cache
    // hit, so the worker must not evict one on its own: an LRU here made a return to the ninth
    // dataset fail with "render tier … is not loaded" until a page reload. The e2e tree has 30
    // artifacts on one 256-cell grid (Task 21 (B1.7)).
    const e2e = path.resolve(import.meta.dirname, 'fixtures/atlas/e2e');
    const e2eCatalog = atlasCatalogSchema.parse(
      JSON.parse(readFileSync(path.join(e2e, 'catalog.json'), 'utf8')),
    );
    const e2eGrid = onlyGrid(e2eCatalog);
    const refs = e2eCatalog.artifacts.slice(0, 9);
    const { dispatch, sent, state } = harness();
    dispatch({
      buf: toBuffer(fixtureBytes(e2e, e2eGrid.entry.url)),
      expect: e2eGrid,
      id: 1,
      type: 'load-grid',
    });
    refs.forEach((artifact, index) =>
      dispatch({
        buf: toBuffer(fixtureBytes(e2e, artifact.web.render.url)),
        id: 2 + index,
        ref: artifact,
        type: 'load-render',
      }),
    );
    for (
      let round = 0;
      round < 50 && !terminal(sent, 1 + refs.length);
      round += 1
    )
      await settle();
    refs.forEach((artifact, index) => {
      expect(terminal(sent, 2 + index)?.type, artifact.id).toBe('render-ready');
      expect(state.renders.has(artifactKeyFor(artifact)), artifact.id).toBe(
        true,
      );
    });
    expect(state.renders.size).toBe(refs.length);
  });
});
