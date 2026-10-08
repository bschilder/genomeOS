/**
 * Snap geometry and gesture rules for the Atlas bottom sheets (mobile sheets
 * design 2026-10-07 §A.1.5). Pure and DOM-free: heights are CSS px of visible
 * sheet, measured up from the explorer's bottom edge.
 */

export type SheetState = 'peek' | 'half' | 'full';

export const SHEET_STATES: readonly SheetState[] = ['peek', 'half', 'full'];
export const DRAG_SLOP_PX = 8;
export const FLICK_PX_PER_MS = 0.5;
export const PROJECTION_MS = 120;
export const TOP_CHROME_GAP_PX = 8;
/** Sub-pixel slack for a flick released on a snap (§A.1.5). */
export const SNAP_TOLERANCE_PX = 1;
const FULL_FRACTION = 0.88;
const HALF_FRACTION = 0.5;
const VELOCITY_WINDOW_MS = 100;

export interface SheetSnaps {
  peek: number;
  half: number;
  full: number;
}

export interface SnapInput {
  explorerHeight: number;
  peekHeight: number;
  topChromeBottom: number;
  dockedHeight: number;
}

export function snapHeights(input: SnapInput): SheetSnaps {
  const height = Math.max(0, input.explorerHeight);
  const peek = Math.min(Math.ceil(input.peekHeight), height);
  const cap = Math.min(
    FULL_FRACTION * height,
    height - input.topChromeBottom - TOP_CHROME_GAP_PX - input.dockedHeight,
  );
  const full = Math.max(peek, Math.floor(cap));
  const half = Math.min(
    full,
    Math.max(peek, Math.round(HALF_FRACTION * height)),
  );
  return { full, half, peek };
}

export function nextSheetState(state: SheetState): SheetState {
  if (state === 'peek') return 'half';
  if (state === 'half') return 'full';
  return 'peek';
}

export function stepSheetState(
  state: SheetState,
  direction: 1 | -1,
): SheetState {
  if (direction > 0) return state === 'peek' ? 'half' : 'full';
  return state === 'full' ? 'half' : 'peek';
}

export function clampSheetHeight(height: number, snaps: SheetSnaps): number {
  return Math.min(snaps.full, Math.max(snaps.peek, height));
}

export function nearestSheetState(
  height: number,
  snaps: SheetSnaps,
): SheetState {
  let best: SheetState = 'peek';
  for (const state of SHEET_STATES) {
    if (Math.abs(snaps[state] - height) < Math.abs(snaps[best] - height))
      best = state;
  }
  return best;
}

/**
 * Where a released drag settles. A flick faster than FLICK_PX_PER_MS goes to
 * the next state at or beyond the release height in its direction, so a fast
 * swipe that already reached a snap is never sent back past it; a release on
 * or within SNAP_TOLERANCE_PX of a snap stays there. Slower releases project
 * PROJECTION_MS ahead and take the nearest state.
 */
export function releaseSheetState(input: {
  height: number;
  velocity: number;
  snaps: SheetSnaps;
}): SheetState {
  const { height, snaps, velocity } = input;
  if (Math.abs(velocity) > FLICK_PX_PER_MS) {
    if (velocity > 0)
      return (
        (['half', 'full'] as const).find(
          (state) => snaps[state] >= height - SNAP_TOLERANCE_PX,
        ) ?? 'full'
      );
    return (
      (['half', 'peek'] as const).find(
        (state) => snaps[state] <= height + SNAP_TOLERANCE_PX,
      ) ?? 'peek'
    );
  }
  const projected = clampSheetHeight(height + velocity * PROJECTION_MS, snaps);
  return nearestSheetState(projected, snaps);
}

export function sheetStateLabel(state: SheetState): string {
  if (state === 'peek') return 'peek';
  return state === 'half' ? 'half height' : 'full height';
}

/**
 * Sheet-height change per millisecond over the 100 ms before release; positive
 * grows the sheet. Pointer events fire only on movement, so the sheet is held at
 * its last sampled height until `now`: a nudge, a hold and a release reads as
 * still, not as a flick.
 */
export class VelocityTracker {
  #samples: { height: number; time: number }[] = [];

  add(height: number, time: number): void {
    this.#samples.push({ height, time });
    while (
      this.#samples.length > 2 &&
      time - this.#samples[0]!.time > VELOCITY_WINDOW_MS
    )
      this.#samples.shift();
  }

  /** `now` is the release time, on the same clock as `add`'s `time`. */
  velocity(now: number): number {
    const first = this.#samples[0];
    const last = this.#samples.at(-1);
    if (!first || !last || first === last) return 0;
    const end = Math.max(now, last.time);
    const start = Math.max(first.time, end - VELOCITY_WINDOW_MS);
    return (last.height - this.#heightAt(start)) / Math.max(1, end - start);
  }

  /** Linear between samples, held at the last height after the last sample. */
  #heightAt(time: number): number {
    const next = this.#samples.findIndex((sample) => sample.time >= time);
    if (next < 0) return this.#samples.at(-1)!.height;
    const after = this.#samples[next]!;
    const before = this.#samples[next - 1];
    if (!before) return after.height;
    return (
      before.height +
      ((after.height - before.height) * (time - before.time)) /
        (after.time - before.time)
    );
  }
}
