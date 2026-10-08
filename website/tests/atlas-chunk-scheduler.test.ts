import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createMessageQueue,
  MAX_BATCH_COST,
  nextBatchCost,
  revealFrameBudgetMs,
  scheduleChunks,
} from '../src/atlas/scene/chunk-scheduler';
import type { ChunkMessage } from '../src/atlas/worker/protocol';
import { fakeRenderLoop, flushTasks } from './helpers/scene-fakes';

function message(chunk: number, seam = false): ChunkMessage {
  return {
    anchors: null,
    artifactKey: 'hbs-rs334:v3:map-2026-08',
    chunk,
    id: 1,
    index: chunk,
    seam,
    support: { chunk, priorDominated: [], unknown: null },
    surface: { chunk } as ChunkMessage['surface'],
    total: 6,
    type: 'chunk',
  };
}

function fakeTarget() {
  const target = {
    added: [] as number[],
    ready: true,
    addChunk(surface: ChunkMessage['surface']) {
      target.added.push(surface.chunk);
    },
    readyCount: () => (target.ready ? target.added.length : 0),
    totalCount: () => target.added.length,
  };
  return target;
}

/** A `document` whose visibility the test flips, firing `visibilitychange` like a browser. */
function fakeDocument(initial: 'hidden' | 'visible') {
  const listeners = new Set<() => void>();
  const page = {
    visibilityState: initial,
    addEventListener(type: string, listener: () => void) {
      if (type === 'visibilitychange') listeners.add(listener);
    },
    removeEventListener(type: string, listener: () => void) {
      if (type === 'visibilitychange') listeners.delete(listener);
    },
  };
  vi.stubGlobal('document', page);
  return {
    get listeners() {
      return listeners.size;
    },
    setVisibility(state: 'hidden' | 'visible') {
      page.visibilityState = state;
      for (const listener of [...listeners]) listener();
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('chunk reveal budget', () => {
  it('sizes the next batch from the measured chunk work', () => {
    expect(nextBatchCost(8, 4, 1)).toBe(2);
    expect(nextBatchCost(50, 40, 4)).toBe(5);
    expect(nextBatchCost(8, 100, 1)).toBe(1);
  });

  it('at most doubles the batch, however cheap one frame measured', () => {
    // Work at or barely above a single baseline sample is noise, not proof
    // that chunks are free, so it never jumps the batch to MAX_BATCH_COST.
    expect(nextBatchCost(8, 0, 1)).toBe(2);
    expect(nextBatchCost(8, -3, 2)).toBe(4);
    expect(nextBatchCost(8, 0.01, 1)).toBe(2);
    expect(nextBatchCost(50, 20, 2)).toBe(4);
    expect(nextBatchCost(8, 0, 40)).toBe(MAX_BATCH_COST);
  });

  it('gives touch devices the 4x-CPU budget', () => {
    expect(revealFrameBudgetMs(false)).toBe(8);
    expect(revealFrameBudgetMs(true)).toBe(50);
  });
});

describe('scheduleChunks', () => {
  it('adds a batch per rendered frame, in camera order, resized to the budget', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    const outcome = scheduleChunks(
      loop as never,
      target,
      [0, 1, 2, 3, 4, 5].map((chunk) => message(chunk)),
      { frameBudgetMs: 8, now: () => clock.now, order: [5, 4, 3, 2, 1, 0] },
    );
    expect(loop.requestRender).toHaveBeenCalledTimes(1);

    loop.frame(2);
    expect(target.added).toEqual([5]);
    loop.frame(6);
    expect(target.added).toEqual([5, 4, 3]);
    loop.frame(10);
    expect(target.added).toEqual([5, 4, 3, 2, 1]);
    loop.frame(10);
    expect(target.added).toEqual([5, 4, 3, 2, 1, 0]);
    loop.frame(6);

    await expect(outcome).resolves.toEqual({
      frames: 4,
      longestFrameMs: 10,
      totalMs: 32,
    });
    expect(loop.postRender.numberOfListeners).toBe(0);
    expect(loop.preUpdate.numberOfListeners).toBe(0);
  });

  it('grows batches gradually after an expensive baseline frame', () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    void scheduleChunks(
      loop as never,
      target,
      Array.from({ length: 12 }, (_, chunk) => message(chunk)),
      { frameBudgetMs: 8, now: () => clock.now, order: [] },
    );

    // The baseline frame also paid for start-up work (30 ms); after it each
    // frame costs 2 ms plus 3 ms per chunk added.
    loop.frame(30);
    expect(target.added).toEqual([0]);
    loop.frame(5);
    expect(target.added).toEqual([0, 1, 2]);
    loop.frame(8);
    expect(target.added).toEqual([0, 1, 2, 3, 4, 5, 6]);
    // Measured against the cheapest frame seen (5 ms), not the 30 ms sample.
    loop.frame(14);
    expect(target.added).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it('rejects, and leaves the render loop running, when the group refuses a chunk', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    const addChunk = target.addChunk;
    target.addChunk = (surface: ChunkMessage['surface']) => {
      if (surface.chunk === 1)
        throw new Error('support chunk 2 does not match surface chunk 1');
      addChunk(surface);
    };
    const outcome = scheduleChunks(
      loop as never,
      target,
      [message(0), message(1)],
      { frameBudgetMs: 8, now: () => clock.now, order: [] },
    );

    loop.frame(1);
    expect(() => loop.frame(1)).not.toThrow();
    await expect(outcome).rejects.toThrow(
      'support chunk 2 does not match surface chunk 1',
    );
    expect(loop.postRender.numberOfListeners).toBe(0);
    expect(loop.preUpdate.numberOfListeners).toBe(0);
  });

  it('rejects, and leaves the render loop running, when a hook throws', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const outcome = scheduleChunks(loop as never, fakeTarget(), [message(0)], {
      frameBudgetMs: 8,
      now: () => clock.now,
      onBeforeAdd: () => {
        throw new Error('observation anchors are missing');
      },
      order: [],
    });

    expect(() => loop.frame(1)).not.toThrow();
    await expect(outcome).rejects.toThrow('observation anchors are missing');
    expect(loop.postRender.numberOfListeners).toBe(0);
  });

  it('waits for the previous batch to be ready before adding more', () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    target.ready = false;
    void scheduleChunks(loop as never, target, [message(0), message(1)], {
      frameBudgetMs: 8,
      now: () => clock.now,
      order: [],
    });

    loop.frame(1);
    loop.frame(1);
    expect(target.added).toEqual([0]);
    expect(loop.requestRender).toHaveBeenCalledTimes(3);

    target.ready = true;
    loop.frame(1);
    expect(target.added).toEqual([0, 1]);
  });

  it('budgets a seam chunk as several ordinary chunks', () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    void scheduleChunks(
      loop as never,
      target,
      [message(0, true), message(1), message(2)],
      { frameBudgetMs: 8, now: () => clock.now, order: [] },
    );

    loop.frame(1);
    expect(target.added).toEqual([0]);
    loop.frame(9);
    expect(target.added).toEqual([0, 1, 2]);
  });

  it('adds at least one chunk per frame however slow the frames are', () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    void scheduleChunks(
      loop as never,
      target,
      [message(0), message(1), message(2)],
      { frameBudgetMs: 1, now: () => clock.now, order: [] },
    );

    loop.frame(1);
    loop.frame(500);
    loop.frame(500);
    expect(target.added).toEqual([0, 1, 2]);
  });

  it('streams worker messages and calls the hooks around each add', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    const calls: string[] = [];
    const queue = createMessageQueue<ChunkMessage>();
    const outcome = scheduleChunks(loop as never, target, queue, {
      frameBudgetMs: 8,
      now: () => clock.now,
      onAdded: ({ chunk }) => calls.push(`added ${chunk}`),
      onBeforeAdd: ({ chunk }) => calls.push(`before ${chunk}`),
      order: [],
    });

    loop.frame(1);
    queue.push(message(0));
    await flushTasks();
    expect(target.added).toEqual([0]);
    loop.frame(1);
    queue.push(message(1));
    queue.end();
    await flushTasks();
    loop.frame(1);

    await expect(outcome).resolves.toMatchObject({ frames: 2 });
    expect(calls).toEqual(['before 0', 'added 0', 'before 1', 'added 1']);
  });

  it('rejects with the worker error when the stream fails', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const queue = createMessageQueue<ChunkMessage>();
    const outcome = scheduleChunks(loop as never, fakeTarget(), queue, {
      frameBudgetMs: 8,
      now: () => clock.now,
      order: [],
    });
    queue.fail(new Error('render tier failed its checksum'));

    await expect(outcome).rejects.toThrow('render tier failed its checksum');
  });

  it('stops adding and detaches when the build is superseded', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    const controller = new AbortController();
    const outcome = scheduleChunks(
      loop as never,
      target,
      [message(0), message(1)],
      {
        frameBudgetMs: 8,
        now: () => clock.now,
        order: [],
        signal: controller.signal,
      },
    );

    loop.frame(1);
    controller.abort();
    await expect(outcome).rejects.toMatchObject({ name: 'AbortError' });
    loop.frame(1);
    expect(target.added).toEqual([0]);
    expect(loop.postRender.numberOfListeners).toBe(0);
  });

  it('records one atlas:chunk-frame measure for the render after each batch', async () => {
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const frames: {
      detail: { artifactKey: string; chunks: number[] };
      end: number;
      start: number;
    }[] = [];
    const outcome = scheduleChunks(
      loop as never,
      fakeTarget(),
      [message(0), message(1)],
      {
        frameBudgetMs: 1,
        measureFrame: (start, end, detail) =>
          frames.push({ detail, end, start }),
        now: () => clock.now,
        order: [],
      },
    );

    loop.frame(1);
    loop.frame(5);
    loop.frame(5);

    await outcome;
    expect(frames).toEqual([
      {
        detail: { artifactKey: 'hbs-rs334:v3:map-2026-08', chunks: [0] },
        end: 6,
        start: 1,
      },
      {
        detail: { artifactKey: 'hbs-rs334:v3:map-2026-08', chunks: [1] },
        end: 11,
        start: 6,
      },
    ]);
  });

  it('does not fail a reveal while the tab is hidden', async () => {
    vi.useFakeTimers();
    const page = fakeDocument('visible');
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const target = fakeTarget();
    const queue = createMessageQueue<ChunkMessage>();
    let settled = false;
    const outcome = scheduleChunks(loop as never, target, queue, {
      frameBudgetMs: 8,
      now: () => clock.now,
      order: [],
      stallTimeoutMs: 100,
    }).catch((error: Error) => error);
    void outcome.then(() => {
      settled = true;
    });

    loop.frame(1);
    await vi.advanceTimersByTimeAsync(60);
    page.setVisibility('hidden');
    // No stall timer runs while hidden, so none frozen with the page fires late on return.
    expect(vi.getTimerCount()).toBe(0);
    // The worker keeps posting while the phone is in another app.
    queue.push(message(0));
    await vi.advanceTimersByTimeAsync(1_000);
    expect(target.added).toEqual([0]);
    expect(vi.getTimerCount()).toBe(0);
    expect(settled).toBe(false);

    // RF1: coming back starts a whole stall window, not what was left of one.
    page.setVisibility('visible');
    await vi.advanceTimersByTimeAsync(99);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await expect(outcome).resolves.toMatchObject({
      message: 'Cesium geometry build timed out',
    });
    expect(page.listeners).toBe(0);
  });

  it('waits out a hidden tab that sends no visibility events', async () => {
    vi.useFakeTimers();
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    let hidden = true;
    let settled = false;
    const outcome = scheduleChunks(
      loop as never,
      fakeTarget(),
      createMessageQueue<ChunkMessage>(),
      {
        frameBudgetMs: 8,
        isHidden: () => hidden,
        now: () => clock.now,
        order: [],
        stallTimeoutMs: 100,
      },
    ).catch((error: Error) => error);
    void outcome.then(() => {
      settled = true;
    });

    loop.frame(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(settled).toBe(false);
    // Without visibilitychange, the return is seen when the timer next fires.
    hidden = false;
    await vi.advanceTimersByTimeAsync(200);
    await expect(outcome).resolves.toMatchObject({
      message: 'Cesium geometry build timed out',
    });
  });

  it('reveals where document has no event target', async () => {
    vi.stubGlobal('document', {});
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const outcome = scheduleChunks(loop as never, fakeTarget(), [message(0)], {
      frameBudgetMs: 8,
      now: () => clock.now,
      order: [],
    });

    loop.frame(1);
    loop.frame(1);
    await expect(outcome).resolves.toMatchObject({ frames: 1 });
  });

  it('fails a reveal that makes no progress', async () => {
    vi.useFakeTimers();
    const clock = { now: 0 };
    const loop = fakeRenderLoop(clock);
    const outcome = scheduleChunks(
      loop as never,
      fakeTarget(),
      createMessageQueue<ChunkMessage>(),
      {
        frameBudgetMs: 8,
        now: () => clock.now,
        order: [],
        stallTimeoutMs: 100,
      },
    ).catch((error: Error) => error);

    loop.frame(1);
    await vi.advanceTimersByTimeAsync(100);
    await expect(outcome).resolves.toMatchObject({
      message: 'Cesium geometry build timed out',
    });
  });
});
