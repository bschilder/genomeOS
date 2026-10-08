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

  it('cuts work into slices of at most the budget and yields between them', async () => {
    let clock = 0;
    const worked: number[] = [];
    const onSlice = vi.fn();
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
    await expect(yieldToEventLoop()).resolves.toBeUndefined();
    expect(abortError().name).toBe('AbortError');
    expect(OVERLAY_SLICE_MS).toBe(8);
  });
});
