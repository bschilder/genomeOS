/** Deterministic Cesium pick arbitration for Atlas design §11. */

import {
  Cartesian2,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Scene,
} from 'cesium';

import type { AtlasPick } from './types';

export interface FrameThrottle<T> {
  queue(value: T): void;
  clear(): void;
  cancel(): void;
}

export function createFrameThrottle<T>(
  action: (value: T) => void,
  requestFrame: (
    callback: FrameRequestCallback,
  ) => number = requestAnimationFrame,
): FrameThrottle<T> {
  let active = true;
  let framePending = false;
  let hasQueuedValue = false;
  let queuedValue: T;
  return {
    queue(value) {
      if (!active) return;
      queuedValue = value;
      hasQueuedValue = true;
      if (framePending) return;
      framePending = true;
      requestFrame(() => {
        framePending = false;
        if (!active || !hasQueuedValue) return;
        hasQueuedValue = false;
        action(queuedValue);
      });
    },
    clear() {
      hasQueuedValue = false;
    },
    cancel() {
      active = false;
      hasQueuedValue = false;
    },
  };
}

function isAtlasPick(value: unknown): value is AtlasPick {
  if (typeof value !== 'object' || value === null || !('kind' in value))
    return false;
  return value.kind === 'surface' || value.kind === 'observation';
}

export function preferredAtlasPick(
  picks: readonly unknown[],
): AtlasPick | null {
  const atlasPicks = picks.flatMap((picked) => {
    const value =
      typeof picked === 'object' && picked !== null && 'id' in picked
        ? picked.id
        : null;
    return isAtlasPick(value) ? [value] : [];
  });
  return (
    atlasPicks.find(({ kind }) => kind === 'observation') ??
    atlasPicks[0] ??
    null
  );
}

export function bindAtlasPicking(
  scene: Scene,
  onSelect: (pick: AtlasPick | null) => void,
  onHover: (pick: AtlasPick | null) => void,
): () => void {
  const handler = new ScreenSpaceEventHandler(scene.canvas);
  handler.setInputAction(
    (event: ScreenSpaceEventHandler.PositionedEvent) =>
      onSelect(preferredAtlasPick(scene.drillPick(event.position, 12))),
    ScreenSpaceEventType.LEFT_CLICK,
  );
  const hoverFrame = createFrameThrottle((position: Cartesian2) =>
    onHover(preferredAtlasPick(scene.drillPick(position, 12))),
  );
  handler.setInputAction(
    (event: ScreenSpaceEventHandler.MotionEvent) =>
      hoverFrame.queue(Cartesian2.clone(event.endPosition)),
    ScreenSpaceEventType.MOUSE_MOVE,
  );
  const leave = () => {
    hoverFrame.clear();
    onHover(null);
  };
  scene.canvas.addEventListener('pointerleave', leave);
  return () => {
    hoverFrame.cancel();
    scene.canvas.removeEventListener('pointerleave', leave);
    handler.destroy();
  };
}
