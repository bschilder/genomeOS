import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ANIMATION_FRAMES,
  createFrameCoalescer,
  type FrameScheduler,
} from '../src/atlas/frame-coalescer';

function fakeFrames() {
  const queued = new Map<number, () => void>();
  let next = 1;
  const scheduler: FrameScheduler = {
    cancel: vi.fn((handle: number) => void queued.delete(handle)),
    request: vi.fn((callback: () => void) => {
      queued.set(next, callback);
      return next++;
    }),
  };
  const runFrame = () => {
    const callbacks = [...queued.values()];
    queued.clear();
    for (const callback of callbacks) callback();
  };
  return { queued, runFrame, scheduler };
}

afterEach(() => vi.unstubAllGlobals());

describe('createFrameCoalescer', () => {
  it('applies only the latest of many pushes, once per frame', () => {
    const { runFrame, scheduler } = fakeFrames();
    const apply = vi.fn();
    const coalescer = createFrameCoalescer(apply, scheduler);
    for (let value = 1; value <= 100; value += 1) coalescer.push(value);
    expect(scheduler.request).toHaveBeenCalledTimes(1);
    expect(apply).not.toHaveBeenCalled();
    runFrame();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(100);
  });

  it('schedules a new frame for a push after the previous frame ran', () => {
    const { runFrame, scheduler } = fakeFrames();
    const apply = vi.fn();
    const coalescer = createFrameCoalescer(apply, scheduler);
    coalescer.push('a');
    runFrame();
    coalescer.push('b');
    runFrame();
    expect(apply.mock.calls).toEqual([['a'], ['b']]);
    expect(scheduler.request).toHaveBeenCalledTimes(2);
  });

  it('drops a pending value when cancelled', () => {
    const { queued, runFrame, scheduler } = fakeFrames();
    const apply = vi.fn();
    const coalescer = createFrameCoalescer(apply, scheduler);
    coalescer.push('stale');
    coalescer.cancel();
    expect(scheduler.cancel).toHaveBeenCalledWith(1);
    expect(queued.size).toBe(0);
    runFrame();
    expect(apply).not.toHaveBeenCalled();
  });

  it('uses requestAnimationFrame by default', () => {
    const request = vi.fn(() => 42);
    const cancel = vi.fn();
    vi.stubGlobal('requestAnimationFrame', request);
    vi.stubGlobal('cancelAnimationFrame', cancel);
    const coalescer = createFrameCoalescer(vi.fn(), ANIMATION_FRAMES);
    coalescer.push(1);
    coalescer.cancel();
    expect(request).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalledWith(42);
  });
});
