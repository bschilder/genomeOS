import { vi } from 'vitest';

/** Minimal stand-in for Cesium's Event with the same remove-callback contract. */
export class FakeEvent {
  readonly #listeners = new Set<() => void>();

  addEventListener(listener: () => void): () => void {
    this.#listeners.add(listener);
    return () => {
      this.#listeners.delete(listener);
    };
  }

  raiseEvent(): void {
    for (const listener of [...this.#listeners]) listener();
  }

  get numberOfListeners(): number {
    return this.#listeners.size;
  }
}

/** One requestRenderMode frame: preUpdate, `workMs` of rendering, postRender. */
export function fakeRenderLoop(clock: { now: number }) {
  const preUpdate = new FakeEvent();
  const postRender = new FakeEvent();
  return {
    postRender,
    preUpdate,
    requestRender: vi.fn(),
    frame(workMs = 0) {
      preUpdate.raiseEvent();
      clock.now += workMs;
      postRender.raiseEvent();
    },
  };
}

export function flushTasks(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
