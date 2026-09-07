/** Render-ready synchronization and visual swaps for Atlas design §11. */

import { Viewer } from 'cesium';

import type { ObservationPrimitiveGroup } from './observation-layer';
import type { ScientificPrimitiveGroup } from './surface-layer';

export type FadeableGroup =
  ScientificPrimitiveGroup | ObservationPrimitiveGroup;

const HEATMAP_TRANSITION_MS = 720;
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
): Promise<void> {
  if (group.isReady()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let readyCount = group.readyCount();
    let timeout = 0;
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
      timeout = window.setTimeout(failIfStalled, GEOMETRY_IDLE_TIMEOUT_MS);
    };
    const remove = viewer.scene.postRender.addEventListener(() => {
      const nextReadyCount = group.readyCount();
      if (nextReadyCount > readyCount) {
        readyCount = nextReadyCount;
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
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const started = performance.now();
    const frame = (now: number) => {
      const progress = transitionProgress(now - started);
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
