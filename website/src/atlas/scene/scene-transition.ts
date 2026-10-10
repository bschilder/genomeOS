/** Render-ready synchronization and visual swaps for Atlas design §11 (spec 2026-10-07 §B.6.8). */

import type { Scene } from 'cesium';

export interface SceneHost {
  scene: Pick<Scene, 'postRender' | 'primitives' | 'requestRender'>;
}

export interface FadeableGroup {
  collection: { show: boolean };
  /** The groups a `fadeTogether` unit stands for; a single group has none. */
  members?: readonly FadeableGroup[];
  isReady(): boolean;
  readyCount(): number;
  totalCount?(): number;
  setOpacity(opacity: number): void;
}

/** One fadeable unit for a surface and its observations, so a swap is atomic.
 *
 * Its `collection` is a view over the members' collections and is never in
 * the scene, so `animateSwap` removes each member's collection instead.
 */
export function fadeTogether(
  ...groups: (FadeableGroup | null | undefined)[]
): FadeableGroup | null {
  const members = groups.flatMap((group) =>
    group ? (group.members ?? [group]) : [],
  );
  if (members.length === 0) return null;
  return {
    members,
    collection: {
      get show() {
        return members.some((member) => member.collection.show);
      },
      set show(value: boolean) {
        for (const member of members) member.collection.show = value;
      },
    },
    isReady: () => members.every((member) => member.isReady()),
    readyCount: () =>
      members.reduce((total, member) => total + member.readyCount(), 0),
    setOpacity(opacity: number) {
      for (const member of members) member.setOpacity(opacity);
    },
    totalCount: () =>
      members.reduce(
        (total, member) =>
          total + (member.totalCount?.() ?? member.readyCount()),
        0,
      ),
  };
}

const HEATMAP_TRANSITION_MS = 720;
const HEATMAP_SWAP_MS = 300;
const GEOMETRY_IDLE_TIMEOUT_MS = 30_000;

export function transitionProgress(
  elapsedMs: number,
  durationMs = HEATMAP_TRANSITION_MS,
): number {
  const linear = Math.min(1, Math.max(0, elapsedMs / durationMs));
  return linear * linear * (3 - 2 * linear);
}

export function waitForReady(
  viewer: SceneHost,
  group: FadeableGroup,
  onProgress?: (progress: number) => void,
): Promise<void> {
  const totalCount = group.totalCount?.() ?? Math.max(group.readyCount(), 1);
  const report = () =>
    onProgress?.(
      totalCount === 0
        ? 1
        : Math.min(1, Math.max(0, group.readyCount() / totalCount)),
    );
  report();
  if (group.isReady()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let readyCount = group.readyCount();
    let timeout: ReturnType<typeof globalThis.setTimeout> | undefined;
    const stopWaiting = () => {
      clearTimeout(timeout);
      remove();
    };
    const failIfStalled = () => {
      group.collection.show = false;
      stopWaiting();
      reject(new Error('Cesium geometry build timed out'));
    };
    const extendDeadline = () => {
      clearTimeout(timeout);
      timeout = globalThis.setTimeout(failIfStalled, GEOMETRY_IDLE_TIMEOUT_MS);
    };
    const remove = viewer.scene.postRender.addEventListener(() => {
      const nextReadyCount = group.readyCount();
      if (nextReadyCount > readyCount) {
        readyCount = nextReadyCount;
        report();
        extendDeadline();
      }
      if (!group.isReady()) return;
      stopWaiting();
      resolve();
    });
    extendDeadline();
    viewer.scene.requestRender();
  });
}

export function animateSwap(
  viewer: SceneHost,
  incoming: FadeableGroup,
  outgoing: FadeableGroup | null,
  reducedMotion: boolean,
  retainOutgoing = false,
  onProgress?: (progress: number) => void,
): Promise<void> {
  const retireOutgoing = () => {
    if (!outgoing) return;
    if (retainOutgoing) {
      outgoing.setOpacity(0);
      outgoing.collection.show = false;
    } else
      for (const group of outgoing.members ?? [outgoing])
        viewer.scene.primitives.remove(group.collection);
  };
  if (reducedMotion) {
    incoming.setOpacity(1);
    retireOutgoing();
    onProgress?.(1);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const started = performance.now();
    onProgress?.(0);
    const frame = (now: number) => {
      const progress = transitionProgress(now - started, HEATMAP_SWAP_MS);
      onProgress?.(progress);
      incoming.setOpacity(progress);
      outgoing?.setOpacity(1 - progress);
      viewer.scene.requestRender();
      if (progress < 1) requestAnimationFrame(frame);
      else {
        retireOutgoing();
        resolve();
      }
    };
    requestAnimationFrame(frame);
  });
}

export function animateValue(
  viewer: { scene: { requestRender(): void } },
  from: number,
  to: number,
  reducedMotion: boolean,
  update: (value: number) => void,
  shouldContinue: () => boolean = () => true,
): Promise<void> {
  if (reducedMotion || from === to) {
    if (shouldContinue()) {
      update(to);
      viewer.scene.requestRender();
    }
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const started = performance.now();
    const frame = (now: number) => {
      if (!shouldContinue()) {
        resolve();
        return;
      }
      const progress = transitionProgress(now - started);
      update(from + (to - from) * progress);
      viewer.scene.requestRender();
      if (progress < 1) requestAnimationFrame(frame);
      else resolve();
    };
    requestAnimationFrame(frame);
  });
}
