import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createAtlasScene } from '../src/atlas/scene/atlas-scene';
import type { AtlasWorkerClient } from '../src/atlas/worker/client';

/** A minimal Cesium Event: listeners in order, removal through the returned function. */
type FakeEvent = ReturnType<typeof fakeEvent>;
function fakeEvent() {
  const listeners = new Set<(...args: unknown[]) => void>();
  return {
    addEventListener(listener: (...args: unknown[]) => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    raiseEvent(...args: unknown[]) {
      for (const listener of listeners) listener(...args);
    },
  };
}

const viewers = vi.hoisted(
  () =>
    [] as {
      options: Record<string, unknown>;
      scene: { renderError: FakeEvent };
      resize: ReturnType<typeof vi.fn>;
      render: ReturnType<typeof vi.fn>;
      destroy: ReturnType<typeof vi.fn>;
    }[],
);

vi.mock('cesium', async (importOriginal) => ({
  ...(await importOriginal<typeof import('cesium')>()),
  Viewer: class {
    readonly scene = {
      primitives: { add: vi.fn() },
      renderError: fakeEvent(),
      requestRender: vi.fn(),
    };
    readonly camera = { moveEnd: fakeEvent() };
    readonly resize = vi.fn();
    readonly render = vi.fn();
    readonly destroy = vi.fn();
    readonly options: Record<string, unknown>;
    constructor(_container: unknown, options: Record<string, unknown>) {
      this.options = options;
      viewers.push(this);
    }
  },
}));
vi.mock('../src/atlas/scene/context-controller', () => ({
  ContextController: class {
    capabilities = () => ({});
    setBasemap = () => Promise.resolve(true);
  },
}));
vi.mock('../src/atlas/scene/context-overlay', () => ({
  ContextOverlay: class {
    load = () => new Promise(() => {});
  },
}));
vi.mock('../src/atlas/scene/scientific-layers', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('../src/atlas/scene/scientific-layers')
  >()),
  ScientificLayers: class {
    destroy = () => {};
  },
}));
vi.mock('../src/atlas/scene/scene-marks', () => ({
  createMarkTracker: () => ({
    destroy: () => {},
    onMark: () => () => {},
    queue: () => {},
  }),
}));
vi.mock('../src/atlas/scene/highlight-layer', () => ({
  HighlightLayer: class {
    collection = {};
  },
}));
vi.mock('../src/atlas/scene/camera', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/atlas/scene/camera')>()),
  bindKeyboardCamera: () => () => {},
  setCameraState: () => {},
}));
vi.mock('../src/atlas/scene/picking', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/atlas/scene/picking')>()),
  bindAtlasPicking: () => () => {},
}));
vi.mock('../src/atlas/scene/scene-policy', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/atlas/scene/scene-policy')>()),
  hideSkyUntilReady: () => () => {},
  styleAtlasScene: () => {},
}));

/** Animation frames that run only when a test advances them. */
let frames: Map<number, () => void>;
let nextFrame: number;
function runFrame(): void {
  const pending = [...frames];
  frames.clear();
  for (const [, callback] of pending) callback();
}

function scene() {
  const controller = createAtlasScene({} as HTMLElement, {
    frameBudgetMs: 8,
    naturalEarthUrl: 'ne.geojson',
    worker: {} as AtlasWorkerClient,
  });
  const viewer = viewers.at(-1)!;
  return { controller, viewer };
}

beforeEach(() => {
  viewers.length = 0;
  frames = new Map();
  nextFrame = 1;
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => {
    frames.set(nextFrame, callback);
    return nextFrame++;
  });
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => {
    frames.delete(handle);
  });
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Atlas render loop (Cesium globe design §12)', () => {
  it('owns the Cesium loop and renders each animation frame', () => {
    const { viewer } = scene();
    expect(viewer.options).toMatchObject({
      showRenderLoopErrors: false,
      useDefaultRenderLoop: false,
    });
    runFrame();
    runFrame();
    expect(viewer.resize).toHaveBeenCalledTimes(2);
    expect(viewer.render).toHaveBeenCalledTimes(2);
    expect(frames.size).toBe(1);
  });

  it('reports an error thrown outside Scene.render once and stops rendering', () => {
    // A throwing postRender or camera moveEnd listener escapes Scene.render's own catch, so
    // Cesium never raises scene.renderError for it.
    const { controller, viewer } = scene();
    const failure = new Error('a postRender listener threw');
    viewer.render.mockImplementation(() => {
      throw failure;
    });
    const listener = vi.fn();
    controller.onRenderError(listener);
    runFrame();
    expect(listener).toHaveBeenCalledExactlyOnceWith(failure);
    expect(frames.size).toBe(0);
    expect(console.error).toHaveBeenCalledOnce();
  });

  it('reports scene.renderError once, even when it is raised again', () => {
    const { controller, viewer } = scene();
    const first = new Error('worker import failed');
    viewer.render.mockImplementation(() => {
      viewer.scene.renderError.raiseEvent({}, first);
      viewer.scene.renderError.raiseEvent(
        {},
        new Error('the same frame again'),
      );
    });
    const listener = vi.fn();
    controller.onRenderError(listener);
    runFrame();
    runFrame();
    expect(listener).toHaveBeenCalledExactlyOnceWith(first);
    expect(viewer.render).toHaveBeenCalledOnce();
    expect(frames.size).toBe(0);
  });

  it('replays the error to a late listener and honours unsubscribe', () => {
    const { controller, viewer } = scene();
    const removed = vi.fn();
    controller.onRenderError(removed)();
    const failure = new Error('lost');
    viewer.scene.renderError.raiseEvent({}, failure);
    expect(removed).not.toHaveBeenCalled();
    const late = vi.fn();
    controller.onRenderError(late);
    expect(late).toHaveBeenCalledExactlyOnceWith(failure);
  });

  it('cancels its frame and reports nothing after destroy', () => {
    const { controller, viewer } = scene();
    const listener = vi.fn();
    controller.onRenderError(listener);
    const renderError = viewer.scene.renderError;
    controller.destroy();
    expect(frames.size).toBe(0);
    expect(viewer.destroy).toHaveBeenCalledOnce();
    renderError.raiseEvent({}, new Error('after destroy'));
    expect(listener).not.toHaveBeenCalled();
    expect(console.error).not.toHaveBeenCalled();
  });
});
