/** The artifact pipeline hook's mark attribution and detail-tier lifecycle (Atlas design §11;
 * spec 2026-10-07 §B.2, §B.6.2, §B.6.8). */
import { afterEach, describe, expect, it, vi } from 'vitest';

// The hook runs without a DOM: React's hooks are replaced by stand-ins that keep refs and state
// across renders and, like a commit, run every cleanup and then every effect whose dependencies
// changed. A render repeats while its effects change state; a state change made later (in a
// promise or a scene listener) is read by the test's next `render`.
const react = vi.hoisted(() => {
  interface EffectSlot {
    cleanup: (() => void) | undefined;
    deps: readonly unknown[] | undefined;
    kind: 'effect';
  }
  interface Pending {
    effect: () => void | (() => void);
    previous: EffectSlot | undefined;
    slot: EffectSlot;
  }
  const state = {
    dirty: false,
    index: 0,
    pending: [] as Pending[],
    slots: [] as unknown[],
  };
  const same = (left?: readonly unknown[], right?: readonly unknown[]) =>
    left !== undefined &&
    right !== undefined &&
    left.length === right.length &&
    left.every((value, index) => Object.is(value, right[index]));
  return {
    commit() {
      const pending = state.pending.splice(0);
      for (const { previous } of pending) previous?.cleanup?.();
      for (const entry of pending)
        entry.slot.cleanup = entry.effect() ?? undefined;
    },
    reset() {
      state.dirty = false;
      state.index = 0;
      state.pending.length = 0;
      state.slots.length = 0;
    },
    state,
    unmount() {
      for (const slot of state.slots as (EffectSlot | undefined)[])
        if (slot?.kind === 'effect') slot.cleanup?.();
    },
    useEffect(effect: () => void | (() => void), deps?: readonly unknown[]) {
      const index = state.index++;
      const previous = state.slots[index] as EffectSlot | undefined;
      if (previous && same(previous.deps, deps)) return;
      const slot: EffectSlot = { cleanup: undefined, deps, kind: 'effect' };
      state.slots[index] = slot;
      state.pending.push({ effect, previous, slot });
    },
    useRef<T>(initial: T) {
      const index = state.index++;
      if (!(index in state.slots)) state.slots[index] = { current: initial };
      return state.slots[index] as { current: T };
    },
    useState<T>(initial: T) {
      const index = state.index++;
      if (!(index in state.slots)) {
        const slot = {
          set(next: T | ((current: T) => T)) {
            const value =
              typeof next === 'function'
                ? (next as (current: T) => T)(slot.value)
                : next;
            if (!Object.is(value, slot.value)) state.dirty = true;
            slot.value = value;
          },
          value: initial,
        };
        state.slots[index] = slot;
      }
      const slot = state.slots[index] as {
        set: (next: T | ((current: T) => T)) => void;
        value: T;
      };
      return [slot.value, slot.set] as const;
    },
  };
});
const paint = vi.hoisted(() => ({ next: vi.fn(() => Promise.resolve()) }));

vi.mock('react', () => ({
  useEffect: react.useEffect,
  useRef: react.useRef,
  useState: react.useState,
}));
vi.mock('../src/components/atlas/useAtlasActivity', () => ({
  nextPaint: () => paint.next(),
}));

import type { ArtifactRef, AtlasCatalog } from '../src/atlas/contracts';
import type { DecodedDetail } from '../src/atlas/gosa/types';
import type { ArtifactLoad, AtlasMark } from '../src/atlas/scene/types';
import {
  artifactKeyFor,
  type SurfaceArtifact,
} from '../src/atlas/surface-columns';
import type { ExplorerState } from '../src/atlas/url-state';
import { AtlasWorkerError } from '../src/atlas/worker/client';
import {
  useArtifactPipeline,
  type ArtifactPipeline,
  type ArtifactPipelineOptions,
} from '../src/components/atlas/useArtifactPipeline';
import { columnarSurface } from './helpers/columnar-surface';

interface Deferred<T> {
  promise: Promise<T>;
  reject(error: unknown): void;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, reject, resolve };
}

const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

const cells = [
  {
    h3: '83754efffffffff',
    post_mean: 0.5,
    post_sd: 0.1,
    support: 'observed' as const,
  },
];

function refFor(id: string): ArtifactRef {
  return {
    data_version: 'map-2026-08',
    id,
    label: `Map ${id}`,
    model_version: 'v3',
    observations_available: false,
  } as ArtifactRef;
}

const refs = { a: refFor('a'), b: refFor('b') };
const keys = { a: artifactKeyFor(refs.a), b: artifactKeyFor(refs.b) };
const catalog = { artifacts: [refs.a, refs.b] } as unknown as AtlasCatalog;

function stateFor(id: 'a' | 'b'): ExplorerState {
  return {
    artifactVersion: 'v3/map-2026-08',
    camera: { lat: 10, lon: 20 },
    elevation: false,
    entityId: id,
    exaggeration: 1,
    view: 'globe',
  } as unknown as ExplorerState;
}

/** The provider's contract: one cached surface per artifact; detail attaches to it on success. */
function fakeProvider() {
  const surfaces = new Map<string, SurfaceArtifact>();
  const details: {
    id: string;
    request: Deferred<DecodedDetail>;
    signal: AbortSignal;
  }[] = [];
  const surfaceOf = (ref: ArtifactRef) => {
    let surface = surfaces.get(ref.id);
    if (!surface) {
      surface = columnarSurface(cells, { id: ref.id });
      surfaces.set(ref.id, surface);
    }
    return surface;
  };
  return {
    details,
    getObservations: vi.fn(() => Promise.resolve(null)),
    getSurface: vi.fn((ref: ArtifactRef) => Promise.resolve(surfaceOf(ref))),
    getSurfaceDetail: vi.fn(async (ref: ArtifactRef, signal?: AbortSignal) => {
      const request = deferred<DecodedDetail>();
      details.push({ id: ref.id, request, signal: signal! });
      const detail = await request.promise;
      surfaceOf(ref).detail = detail;
      return detail;
    }),
  };
}

function fakeScene() {
  const commits = new Set<(artifactKey: string) => void>();
  const marks = new Set<(mark: AtlasMark) => void>();
  const loads: ArtifactLoad[] = [];
  /** One settlement per `setArtifact` call, in call order. */
  const results: Deferred<void>[] = [];
  return {
    commit(artifactKey: string) {
      for (const listener of [...commits]) listener(artifactKey);
    },
    displayedLayer: () => null,
    loads,
    mark(mark: AtlasMark) {
      for (const listener of [...marks]) listener(mark);
    },
    markValuesReady: vi.fn<(artifactKey: string) => void>(),
    onCommit(listener: (artifactKey: string) => void) {
      commits.add(listener);
      return () => void commits.delete(listener);
    },
    onMark(listener: (mark: AtlasMark) => void) {
      marks.add(listener);
      return () => void marks.delete(listener);
    },
    removeSurface: vi.fn<(artifactKey: string) => void>(),
    results,
    setArtifact: vi.fn((load: ArtifactLoad) => {
      loads.push(load);
      const result = deferred<void>();
      results.push(result);
      return result.promise;
    }),
    setCamera: vi.fn(),
    setElevation: vi.fn(() => Promise.resolve()),
    setSceneMode: vi.fn(() => Promise.resolve()),
    setSelection: vi.fn(),
  };
}

type FakeScene = ReturnType<typeof fakeScene>;

function mountPipeline() {
  const provider = fakeProvider();
  let nextId = 0;
  const activity = {
    begin: vi.fn(() => ++nextId),
    fail: vi.fn<(id: number) => void>(),
    finish: vi.fn<(id: number) => void>(),
    update: vi.fn(),
  };
  const onArtifactChange = vi.fn();
  const setError = vi.fn<(message: string | null) => void>();
  const base: Omit<ArtifactPipelineOptions, 'controller' | 'state'> = {
    activity,
    appliedDisplay: { current: null },
    cameraApplied: { current: false },
    catalog,
    dataAttempt: 0,
    onArtifactChange,
    provider,
    reducedMotion: true,
    setError,
  };
  const render = (id: 'a' | 'b', scene: FakeScene | null): ArtifactPipeline => {
    const options: ArtifactPipelineOptions = {
      ...base,
      controller: scene as unknown as ArtifactPipelineOptions['controller'],
      state: stateFor(id),
    };
    for (let pass = 0; pass < 10; pass++) {
      react.state.dirty = false;
      react.state.index = 0;
      const pipeline = useArtifactPipeline(options);
      react.commit();
      if (!react.state.dirty) return pipeline;
    }
    throw new Error('The pipeline kept changing state on every render');
  };
  return { activity, onArtifactChange, provider, render, setError };
}

afterEach(() => {
  react.unmount();
  react.reset();
  paint.next.mockReset();
  paint.next.mockImplementation(() => Promise.resolve());
});

describe('artifact pipeline marks', () => {
  it('attributes marks to the artifact handed to the scene, not to a newer request', async () => {
    const { provider, render } = mountPipeline();
    const scene = fakeScene();
    render('a', scene);
    await settle();
    expect(scene.loads.map((load) => load.artifactKey)).toEqual([keys.a]);
    // B is requested and downloaded, but its handoff has not reached the scene yet.
    paint.next.mockReturnValueOnce(new Promise(() => undefined));
    render('b', scene);
    await settle();
    scene.mark('surface-first-chunk');
    scene.mark('surface-visible');
    const pipeline = render('b', scene);
    expect(pipeline.revealing?.artifactKey).toBe(keys.a);
    expect(pipeline.revealLegend).toBe(true);
    expect(pipeline.targetRef.current?.artifactKey).toBe(keys.a);
    expect(provider.getSurfaceDetail.mock.calls.map(([ref]) => ref.id)).toEqual(
      ['a'],
    );
  });

  it('drops a cold reveal once the scene is handed another artifact', async () => {
    const { render } = mountPipeline();
    const scene = fakeScene();
    render('a', scene);
    await settle();
    scene.mark('surface-first-chunk');
    expect(render('a', scene).revealing?.artifactKey).toBe(keys.a);
    render('b', scene);
    await settle();
    expect(scene.loads.map((load) => load.artifactKey)).toEqual([
      keys.a,
      keys.b,
    ]);
    let pipeline = render('b', scene);
    expect(pipeline.revealing).toBeNull();
    expect(pipeline.revealLegend).toBe(false);
    expect(pipeline.targetRef.current).toBeNull();
    scene.mark('observations-visible');
    pipeline = render('b', scene);
    expect(pipeline.revealing?.artifactKey).toBe(keys.b);
    expect(pipeline.revealLegend).toBe(false);
  });

  it('reads marks against the displayed artifact again after a request fails', async () => {
    const { provider, render, setError } = mountPipeline();
    const scene = fakeScene();
    render('a', scene);
    await settle();
    scene.commit(keys.a);
    render('b', scene);
    await settle();
    expect(scene.loads.map((load) => load.artifactKey)).toEqual([
      keys.a,
      keys.b,
    ]);
    scene.results[1].reject(new Error('render tier failed its checksum'));
    await settle();
    expect(setError).toHaveBeenLastCalledWith(
      'b: render tier failed its checksum',
    );
    // A style change now rebuilds the displayed artifact, whose epoch the marks describe.
    scene.mark('surface-visible');
    expect(provider.getSurfaceDetail.mock.calls.map(([ref]) => ref.id)).toEqual(
      ['a'],
    );
  });
});

describe('artifact pipeline detail tier', () => {
  it('marks values ready on a new scene when the detail tier is already attached', async () => {
    const { provider, render } = mountPipeline();
    const first = fakeScene();
    render('a', first);
    await settle();
    first.mark('surface-visible');
    provider.details[0].request.resolve(
      columnarSurface(cells, { withDetail: true }).detail!,
    );
    await settle();
    expect(first.markValuesReady).toHaveBeenCalledWith(keys.a);
    // "Retry globe": a new scene reveals the cached surface, whose detail tier is attached.
    const second = fakeScene();
    render('a', second);
    await settle();
    expect(second.loads.map((load) => load.artifactKey)).toEqual([keys.a]);
    second.mark('surface-visible');
    expect(second.markValuesReady).toHaveBeenCalledWith(keys.a);
    expect(provider.getSurfaceDetail).toHaveBeenCalledTimes(1);
    second.commit(keys.a);
    expect(render('a', second).detailStatus).toBe('ready');
  });

  it('removes the surface and reports the error when the displayed detail tier is corrupt', async () => {
    const { activity, onArtifactChange, provider, render, setError } =
      mountPipeline();
    const scene = fakeScene();
    render('a', scene);
    await settle();
    scene.commit(keys.a);
    scene.mark('surface-visible');
    onArtifactChange.mockClear();
    provider.details[0].request.reject(
      new AtlasWorkerError('checksum', 'detail tier checksum mismatch', null),
    );
    await settle();
    expect(scene.removeSurface).toHaveBeenCalledWith(keys.a);
    expect(onArtifactChange).toHaveBeenCalledTimes(1);
    expect(setError).toHaveBeenLastCalledWith(
      'a: detail tier checksum mismatch',
    );
    expect(activity.fail).toHaveBeenCalledTimes(1);
    expect(render('a', scene).detailStatus).toBe('invalid');
  });

  it('aborts a left artifact’s detail tier at the commit that leaves it and reports nothing', async () => {
    const { activity, onArtifactChange, provider, render, setError } =
      mountPipeline();
    const scene = fakeScene();
    render('a', scene);
    await settle();
    scene.commit(keys.a);
    scene.mark('surface-visible');
    const detail = provider.details[0];
    expect(detail.id).toBe('a');
    render('b', scene);
    await settle();
    scene.commit(keys.b);
    expect(detail.signal.aborted).toBe(true);
    onArtifactChange.mockClear();
    setError.mockClear();
    // A corrupt result that lands after the abort still belongs to the artifact the user left.
    detail.request.reject(
      new AtlasWorkerError('checksum', 'detail tier checksum mismatch', null),
    );
    await settle();
    expect(scene.removeSurface).not.toHaveBeenCalled();
    expect(onArtifactChange).not.toHaveBeenCalled();
    expect(setError).not.toHaveBeenCalled();
    expect(activity.fail).not.toHaveBeenCalled();
    expect(render('b', scene).detailStatus).toBe('loading');
  });

  it('ignores a detail failure of a cold reveal the user has already left', async () => {
    const { activity, onArtifactChange, provider, render, setError } =
      mountPipeline();
    const scene = fakeScene();
    render('a', scene);
    await settle();
    scene.mark('surface-visible');
    paint.next.mockReturnValueOnce(new Promise(() => undefined));
    render('b', scene);
    await settle();
    setError.mockClear();
    provider.details[0].request.reject(
      new AtlasWorkerError('validation', 'interval_order: q025 > mean', null),
    );
    await settle();
    expect(scene.removeSurface).not.toHaveBeenCalled();
    expect(onArtifactChange).not.toHaveBeenCalled();
    expect(setError).not.toHaveBeenCalled();
    expect(activity.fail).not.toHaveBeenCalled();
  });

  it('does not stall the incoming artifact when the still-displayed one has a corrupt detail tier', async () => {
    // Task 66 ruling (progress.md:1030): during an A→B switch A stays displayed until B's commit,
    // so A's late detail failure must neither remove anything nor take over B's activity, or
    // data-atlas-ready stays "false" on a healthy B under A's error (final review correctness-2).
    const { activity, onArtifactChange, provider, render, setError } =
      mountPipeline();
    // useAtlasActivity's rule: only the latest begin() may finish.
    let latest = 0;
    let status = 'loading';
    activity.begin.mockImplementation(() => {
      latest += 1;
      status = 'loading';
      return latest;
    });
    activity.finish.mockImplementation((id: number) => {
      if (id === latest) status = 'ready';
    });
    const scene = fakeScene();
    render('a', scene);
    await settle();
    scene.results[0].resolve();
    await settle();
    scene.commit(keys.a);
    scene.mark('surface-visible');
    expect(status).toBe('ready');
    expect(provider.details[0].id).toBe('a');

    // The user picks B; B's handoff reaches the scene and is still building.
    render('b', scene);
    await settle();
    expect(scene.loads.at(-1)?.artifactKey).toBe(keys.b);
    setError.mockClear();
    onArtifactChange.mockClear();

    // A's detail tier (still displayed, its request not yet aborted) turns out corrupt.
    provider.details[0].request.reject(
      new AtlasWorkerError('checksum', 'detail tier checksum mismatch', null),
    );
    await settle();
    expect(scene.removeSurface).not.toHaveBeenCalled();
    expect(onArtifactChange).not.toHaveBeenCalled();
    expect(setError).not.toHaveBeenCalled();
    expect(activity.fail).not.toHaveBeenCalled();

    // B finishes and commits normally, and the map is marked ready.
    scene.results[1].resolve();
    await settle();
    scene.commit(keys.b);
    render('b', scene);
    expect(status).toBe('ready');
  });
});
