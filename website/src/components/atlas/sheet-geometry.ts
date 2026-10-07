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

export function releaseSheetState(input: {
  from: SheetState;
  height: number;
  velocity: number;
  snaps: SheetSnaps;
}): SheetState {
  if (Math.abs(input.velocity) > FLICK_PX_PER_MS)
    return stepSheetState(input.from, input.velocity > 0 ? 1 : -1);
  const projected = clampSheetHeight(
    input.height + input.velocity * PROJECTION_MS,
    input.snaps,
  );
  return nearestSheetState(projected, input.snaps);
}

export function sheetStateLabel(state: SheetState): string {
  if (state === 'peek') return 'peek';
  return state === 'half' ? 'half height' : 'full height';
}

/** Sheet-height change per millisecond over the last 100 ms; positive grows the sheet. */
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

  velocity(): number {
    const first = this.#samples[0];
    const last = this.#samples.at(-1);
    if (!first || !last || first === last) return 0;
    return (last.height - first.height) / Math.max(1, last.time - first.time);
  }
}
