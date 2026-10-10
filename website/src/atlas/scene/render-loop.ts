/**
 * The Atlas-owned Cesium render loop and its one-shot failure report (Cesium globe design §12).
 *
 * Cesium raises `scene.renderError` only for errors inside Scene.render's guarded blocks. An error
 * from a preUpdate, postUpdate or postRender listener, a camera moveStart/moveEnd listener, the
 * clock tick or resize lands in the default loop's own catch instead, which stops the loop without
 * raising that event. Owning the loop sends both paths to `fail`. A transient failure such as a
 * worker module that did not download fails every later frame, and the document-wide geometry
 * workers keep that failed import, so the error is reported once and recovery is a fresh page (the
 * explorer's Retry globe), never a restarted loop or a new scene.
 *
 * The build bundles this module into the Cesium chunk (astro.config.mjs): its tick is the
 * resize-and-render work Cesium's default loop did there, and the cold-load harness attributes
 * long animation frames by script source (fast-load design §B.1).
 */

/** Frame scheduling, injectable so the loop unit-tests without a browser. */
export interface FrameScheduler {
  request(callback: () => void): number;
  cancel(handle: number): void;
}

const ANIMATION_FRAMES: FrameScheduler = {
  request: (callback) => requestAnimationFrame(callback),
  cancel: (handle) => cancelAnimationFrame(handle),
};

export class RenderLoop {
  readonly #renderFrame: () => void;
  readonly #scheduler: FrameScheduler;
  readonly #listeners = new Set<(error: unknown) => void>();
  #failure: { error: unknown } | null = null;
  #frame: number | null = null;
  #stopped = false;

  constructor(
    renderFrame: () => void,
    scheduler: FrameScheduler = ANIMATION_FRAMES,
  ) {
    this.#renderFrame = renderFrame;
    this.#scheduler = scheduler;
  }

  start(): void {
    if (this.#frame === null && !this.#stopped && !this.#failure)
      this.#frame = this.#scheduler.request(this.#tick);
  }

  readonly #tick = (): void => {
    this.#frame = null;
    if (this.#stopped || this.#failure) return;
    try {
      this.#renderFrame();
    } catch (error) {
      this.fail(error);
    }
    this.start();
  };

  /** Stops rendering and reports the first error once; later errors and errors after stop are ignored. */
  fail(error: unknown): void {
    if (this.#stopped || this.#failure) return;
    this.#failure = { error };
    this.#cancelFrame();
    console.error('The Atlas globe stopped rendering.', error);
    for (const listener of this.#listeners) listener(error);
  }

  /** A listener added after the failure still hears it. */
  onError(listener: (error: unknown) => void): () => void {
    this.#listeners.add(listener);
    if (this.#failure) listener(this.#failure.error);
    return () => {
      this.#listeners.delete(listener);
    };
  }

  stop(): void {
    this.#stopped = true;
    this.#cancelFrame();
    this.#listeners.clear();
  }

  #cancelFrame(): void {
    if (this.#frame !== null) this.#scheduler.cancel(this.#frame);
    this.#frame = null;
  }
}
