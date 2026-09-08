/** Deterministic Cesium pick arbitration for Atlas design §11. */

import {
  Cartesian2,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Scene,
} from 'cesium';

import type { AtlasHover, AtlasPick } from './types';

export interface FrameThrottle<T> {
  queue(value: T): void;
  clear(): void;
  cancel(): void;
}

export interface StableHover<T> {
  update(value: T | null): void;
  cancel(): void;
}

export interface DragTracker {
  down(position: Cartesian2): void;
  move(position: Cartesian2): boolean;
  up(): void;
}

export function createDragTracker(
  onDragStart: (position: Cartesian2) => void,
  thresholdPixels = 5,
): DragTracker {
  let downPosition: Cartesian2 | null = null;
  let dragging = false;
  return {
    down(position) {
      downPosition = Cartesian2.clone(position);
      dragging = false;
    },
    move(position) {
      if (!downPosition) return false;
      if (
        !dragging &&
        Cartesian2.distance(downPosition, position) > thresholdPixels
      ) {
        dragging = true;
        onDragStart(Cartesian2.clone(position));
      }
      return dragging;
    },
    up() {
      downPosition = null;
      dragging = false;
    },
  };
}

export function createStableHover<T>(
  action: (value: T | null) => void,
  same: (first: T, second: T) => boolean,
  leaveDelayMs = 90,
): StableHover<T> {
  let active = true;
  let current: T | null = null;
  let leaveTimer: ReturnType<typeof setTimeout> | null = null;
  const cancelLeave = () => {
    if (leaveTimer !== null) clearTimeout(leaveTimer);
    leaveTimer = null;
  };
  return {
    update(value) {
      if (!active) return;
      if (value) {
        cancelLeave();
        if (current && same(current, value)) return;
        current = value;
        action(value);
        return;
      }
      if (!current || leaveTimer !== null) return;
      leaveTimer = setTimeout(() => {
        leaveTimer = null;
        current = null;
        action(null);
      }, leaveDelayMs);
    },
    cancel() {
      active = false;
      cancelLeave();
    },
  };
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

export function sameAtlasPick(first: AtlasPick, second: AtlasPick): boolean {
  if (first.kind === 'surface')
    return second.kind === 'surface' && first.h3Index === second.h3Index;
  return (
    second.kind === 'observation' &&
    first.sourceRecordId === second.sourceRecordId
  );
}

export function sameAtlasHover(first: AtlasHover, second: AtlasHover): boolean {
  return sameAtlasPick(first.pick, second.pick);
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

export function atlasHoverForPicks(
  picks: readonly unknown[],
  position: Cartesian2,
): AtlasHover | null {
  const pick = preferredAtlasPick(picks);
  return pick
    ? { pick, screenPosition: { x: position.x, y: position.y } }
    : null;
}

export function bindAtlasPicking(
  scene: Scene,
  onSelect: (pick: AtlasPick | null) => void,
  onHover: (hover: AtlasHover | null) => void,
): () => void {
  const handler = new ScreenSpaceEventHandler(scene.canvas);
  handler.setInputAction(
    (event: ScreenSpaceEventHandler.PositionedEvent) =>
      onSelect(preferredAtlasPick(scene.drillPick(event.position, 12))),
    ScreenSpaceEventType.LEFT_CLICK,
  );
  const stableHover = createStableHover(onHover, sameAtlasHover);
  const drag = createDragTracker(() => {
    hoverFrame.clear();
    stableHover.update(null);
  });
  const hoverFrame = createFrameThrottle((position: Cartesian2) => {
    stableHover.update(
      atlasHoverForPicks(scene.drillPick(position, 12), position),
    );
  });
  handler.setInputAction(
    (event: ScreenSpaceEventHandler.PositionedEvent) =>
      drag.down(event.position),
    ScreenSpaceEventType.LEFT_DOWN,
  );
  handler.setInputAction(() => drag.up(), ScreenSpaceEventType.LEFT_UP);
  handler.setInputAction((event: ScreenSpaceEventHandler.MotionEvent) => {
    const position = Cartesian2.clone(event.endPosition);
    if (drag.move(position)) {
      hoverFrame.clear();
      return;
    }
    hoverFrame.queue(position);
  }, ScreenSpaceEventType.MOUSE_MOVE);
  const leave = () => {
    hoverFrame.clear();
    drag.up();
    stableHover.update(null);
  };
  scene.canvas.addEventListener('pointerleave', leave);
  return () => {
    hoverFrame.cancel();
    stableHover.cancel();
    scene.canvas.removeEventListener('pointerleave', leave);
    handler.destroy();
  };
}
