/** Render-ready synchronization and visual swaps for Atlas design §11. */

import { Viewer } from 'cesium';

import type { ObservationPrimitiveGroup } from './observation-layer';
import type { ScientificPrimitiveGroup } from './surface-layer';

export type FadeableGroup =
  ScientificPrimitiveGroup | ObservationPrimitiveGroup;

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
  viewer: Viewer,
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
      timeout = globalThis.setTimeout(
        failIfStalled,
        GEOMETRY_IDLE_TIMEOUT_MS,
      );
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
  viewer: Viewer,
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
    } else viewer.scene.primitives.remove(outgoing.collection);
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
  viewer: Viewer,
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
