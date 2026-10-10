import { describe, expect, it, vi } from 'vitest';

import {
  abortError,
  edgeRendererForMode,
  OVERLAY_SLICE_MS,
  runSliced,
  yieldToEventLoop,
} from '../src/atlas/scene/sliced-lines';

describe('frame-budgeted overlay slices', () => {
  it('keeps BufferPolylineCollection to the 3D globe', () => {
    expect(edgeRendererForMode('globe')).toBe('buffer');
    expect(edgeRendererForMode('map')).toBe('projected');
    expect(edgeRendererForMode('perspective')).toBe('projected');
  });

  it('starts no new item once the budget has elapsed, calls onSlice after each slice and yields between them', async () => {
    let clock = 0;
    const worked: number[] = [];
    const sliceEnds: number[] = [];
    const onSlice = vi.fn(() => {
      sliceEnds.push(worked.length);
    });
    const yieldFn = vi.fn(() => Promise.resolve());

    const slices = await runSliced(
      7,
      (index) => {
        worked.push(index);
        clock += 3;
      },
      { now: () => clock, onSlice, sliceMs: 8, yieldFn },
    );

    expect(worked).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(slices).toBe(3);
    // 3 ms items against an 8 ms budget: the third item starts at 6 ms and
    // runs the slice to 9 ms, so slices are [0, 1, 2], [3, 4, 5], [6].
    expect(sliceEnds).toEqual([3, 6, 7]);
    expect(onSlice).toHaveBeenCalledTimes(3);
    expect(yieldFn).toHaveBeenCalledTimes(2);
  });

  it('always makes progress when one item exceeds the budget', async () => {
    let clock = 0;
    const slices = await runSliced(
      3,
      () => {
        clock += 50;
      },
      { now: () => clock, sliceMs: 8, yieldFn: () => Promise.resolve() },
    );
    expect(slices).toBe(3);
  });

  it('stops at the next slice boundary once aborted', async () => {
    const controller = new AbortController();
    let clock = 0;
    const worked: number[] = [];
    const outcome = runSliced(
      10,
      (index) => {
        worked.push(index);
        clock += 10;
        if (index === 0) controller.abort();
      },
      {
        now: () => clock,
        signal: controller.signal,
        sliceMs: 8,
        yieldFn: () => Promise.resolve(),
      },
    );

    await expect(outcome).rejects.toMatchObject({ name: 'AbortError' });
    expect(worked).toEqual([0]);
  });

  it('yields through a MessageChannel task', async () => {
    const deliveries: Array<() => void> = [];
    let closed = 0;
    class RecordingChannel {
      readonly port1 = {
        onmessage: null as (() => void) | null,
        close: () => {
          closed += 1;
        },
      };
      readonly port2 = {
        postMessage: () => {
          deliveries.push(() => this.port1.onmessage?.());
        },
      };
    }
    vi.stubGlobal('MessageChannel', RecordingChannel);
    try {
      let resolved = false;
      const yielded = yieldToEventLoop().then(() => {
        resolved = true;
      });
      await drainMicrotasks();
      // One message is posted and nothing resolves until it is delivered, so
      // neither a microtask nor a timer can stand in for the channel.
      expect(deliveries).toHaveLength(1);
      expect(resolved).toBe(false);

      deliveries[0]();
      await yielded;
      expect(resolved).toBe(true);
      expect(closed).toBe(1);

      // runSliced yields through the same channel when no yieldFn is given.
      let clock = 0;
      const sliced = runSliced(
        2,
        () => {
          clock += 10;
        },
        { now: () => clock, sliceMs: 8 },
      );
      await drainMicrotasks();
      expect(deliveries).toHaveLength(2);
      deliveries[1]();
      await expect(sliced).resolves.toBe(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('resolves after the microtask queue drains with the real MessageChannel', async () => {
    let resolved = false;
    const yielded = yieldToEventLoop().then(() => {
      resolved = true;
    });
    await drainMicrotasks();
    expect(resolved).toBe(false);
    await expect(yielded).resolves.toBeUndefined();
    expect(resolved).toBe(true);
  });

  it('names its constants and abort error', () => {
    expect(abortError().name).toBe('AbortError');
    expect(OVERLAY_SLICE_MS).toBe(8);
  });
});

async function drainMicrotasks(rounds = 20): Promise<void> {
  for (let round = 0; round < rounds; round += 1) await Promise.resolve();
}
