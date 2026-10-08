/** At most one state update per animation frame for streamed progress (fast-load design §B.6.12). */

export interface FrameScheduler {
  cancel(handle: number): void;
  request(callback: () => void): number;
}

export const ANIMATION_FRAMES: FrameScheduler = {
  cancel: (handle) => cancelAnimationFrame(handle),
  request: (callback) => requestAnimationFrame(() => callback()),
};

export interface FrameCoalescer<T> {
  cancel(): void;
  push(value: T): void;
}

export function createFrameCoalescer<T>(
  apply: (value: T) => void,
  scheduler: FrameScheduler = ANIMATION_FRAMES,
): FrameCoalescer<T> {
  let handle: number | null = null;
  let latest: { value: T } | null = null;
  return {
    cancel() {
      if (handle !== null) scheduler.cancel(handle);
      handle = null;
      latest = null;
    },
    push(value) {
      latest = { value };
      if (handle !== null) return;
      handle = scheduler.request(() => {
        handle = null;
        const next = latest;
        latest = null;
        if (next) apply(next.value);
      });
    },
  };
}
