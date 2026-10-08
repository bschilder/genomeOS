/** Deterministic Cesium pick arbitration for Atlas design §11. */

import {
  Cartesian2,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Scene,
} from 'cesium';

import type { AtlasHover, AtlasPick, AtlasPickId } from './types';

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

export type PickResolver = (
  picks: readonly unknown[],
  position: Cartesian2,
) => AtlasPick | null;

function pickIdOf(picked: unknown): AtlasPickId | null {
  const value =
    typeof picked === 'object' && picked !== null && 'id' in picked
      ? picked.id
      : null;
  if (typeof value !== 'object' || value === null || !('kind' in value))
    return null;
  return value.kind === 'surface' ||
    value.kind === 'surface-chunk' ||
    value.kind === 'observation'
    ? (value as AtlasPickId)
    : null;
}

export function sameAtlasPick(first: AtlasPick, second: AtlasPick): boolean {
  if (first.kind === 'surface')
    return (
      second.kind === 'surface' &&
      first.artifactKey === second.artifactKey &&
      first.row === second.row &&
      first.h3Index === second.h3Index
    );
  return (
    second.kind === 'observation' &&
    first.artifactKey === second.artifactKey &&
    first.sourceRecordId === second.sourceRecordId
  );
}

export function sameAtlasHover(first: AtlasHover, second: AtlasHover): boolean {
  return sameAtlasPick(first.pick, second.pick);
}

/**
 * Observations win over surface cells. With a displayed artifact key (the
 * chunk pipeline), picks of any other artifact are dropped before choosing,
 * so an incoming group shown at opacity 0 during a swap can never answer for
 * the displayed one (spec 2026-10-07 §B.6.6).
 */
export function preferredAtlasPick(
  picks: readonly unknown[],
  displayedKey?: string | null,
): AtlasPickId | null {
  const candidates = picks.flatMap((picked): AtlasPickId[] => {
    const id = pickIdOf(picked);
    if (!id) return [];
    if (displayedKey === undefined)
      return id.kind === 'surface-chunk' ? [] : [id];
    return id.kind !== 'surface' && id.artifactKey === displayedKey ? [id] : [];
  });
  return (
    candidates.find(({ kind }) => kind === 'observation') ??
    candidates[0] ??
    null
  );
}

export const legacyPickResolver: PickResolver = (picks) => {
  const pick = preferredAtlasPick(picks);
  return pick && pick.kind !== 'surface-chunk' ? pick : null;
};

export function atlasHoverForPicks(
  picks: readonly unknown[],
  position: Cartesian2,
): AtlasHover | null {
  const pick = legacyPickResolver(picks, position);
  return pick
    ? { pick, screenPosition: { x: position.x, y: position.y } }
    : null;
}

export function bindAtlasPicking(
  scene: Scene,
  onSelect: (pick: AtlasPick | null) => void,
  onHover: (hover: AtlasHover | null) => void,
  resolve: PickResolver = legacyPickResolver,
): () => void {
  const handler = new ScreenSpaceEventHandler(scene.canvas);
  handler.setInputAction(
    (event: ScreenSpaceEventHandler.PositionedEvent) =>
      onSelect(resolve(scene.drillPick(event.position, 12), event.position)),
    ScreenSpaceEventType.LEFT_CLICK,
  );
  const stableHover = createStableHover(onHover, sameAtlasHover);
  const drag = createDragTracker(() => {
    hoverFrame.clear();
    stableHover.update(null);
  });
  const hoverFrame = createFrameThrottle((position: Cartesian2) => {
    const pick = resolve(scene.drillPick(position, 12), position);
    stableHover.update(
      pick ? { pick, screenPosition: { x: position.x, y: position.y } } : null,
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
