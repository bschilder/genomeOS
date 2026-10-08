import { describe, expect, it } from 'vitest';

import {
  DRAG_SLOP_PX,
  FLICK_PX_PER_MS,
  PROJECTION_MS,
  TOP_CHROME_GAP_PX,
  VelocityTracker,
  clampSheetHeight,
  nearestSheetState,
  nextSheetState,
  releaseSheetState,
  sheetStateLabel,
  snapHeights,
  stepSheetState,
  type SheetSnaps,
} from '../src/components/atlas/sheet-geometry';

const PHONE = {
  dockedHeight: 90,
  explorerHeight: 757,
  peekHeight: 78,
  topChromeBottom: 70,
};
const SNAPS: SheetSnaps = { full: 589, half: 379, peek: 78 };

describe('bottom-sheet snaps and gestures (mobile sheets design §A.1.5)', () => {
  it('pins the gesture constants from the design', () => {
    expect(DRAG_SLOP_PX).toBe(8);
    expect(FLICK_PX_PER_MS).toBe(0.5);
    expect(PROJECTION_MS).toBe(120);
    expect(TOP_CHROME_GAP_PX).toBe(8);
  });

  it('caps full below the top chrome and the docked legend and credits', () => {
    expect(snapHeights(PHONE)).toEqual(SNAPS);
  });

  it('uses 88 % of the explorer when the chrome leaves more room', () => {
    expect(
      snapHeights({
        dockedHeight: 0,
        explorerHeight: 700,
        peekHeight: 60,
        topChromeBottom: 0,
      }).full,
    ).toBe(616);
  });

  it('never lets full fall below peek or half rise above full', () => {
    expect(
      snapHeights({
        dockedHeight: 120,
        explorerHeight: 300,
        peekHeight: 70,
        topChromeBottom: 200,
      }),
    ).toEqual({ full: 70, half: 70, peek: 70 });
    const crowded = snapHeights({
      dockedHeight: 100,
      explorerHeight: 700,
      peekHeight: 70,
      topChromeBottom: 300,
    });
    expect(crowded.full).toBe(292);
    expect(crowded.half).toBe(292);
  });

  it('cycles peek → half → full → peek and steps without wrapping', () => {
    expect(nextSheetState('peek')).toBe('half');
    expect(nextSheetState('half')).toBe('full');
    expect(nextSheetState('full')).toBe('peek');
    expect(stepSheetState('peek', 1)).toBe('half');
    expect(stepSheetState('full', 1)).toBe('full');
    expect(stepSheetState('full', -1)).toBe('half');
    expect(stepSheetState('peek', -1)).toBe('peek');
  });

  it('names the states for the handle', () => {
    expect(sheetStateLabel('peek')).toBe('peek');
    expect(sheetStateLabel('half')).toBe('half height');
    expect(sheetStateLabel('full')).toBe('full height');
  });

  it('settles a flick at the next state at or beyond the release height', () => {
    // A fast swipe that already reached (or passed) a snap is not sent back.
    expect(
      releaseSheetState({ height: 560, snaps: SNAPS, velocity: 0.8 }),
    ).toBe('full');
    expect(
      releaseSheetState({ height: 100, snaps: SNAPS, velocity: -0.6 }),
    ).toBe('peek');
    expect(releaseSheetState({ height: 589, snaps: SNAPS, velocity: 2 })).toBe(
      'full',
    );
    expect(releaseSheetState({ height: 78, snaps: SNAPS, velocity: -2 })).toBe(
      'peek',
    );
    // From peek, an up flick released on or within 1 px of half (379) stays
    // there, so a sub-pixel miss (376.25 vs 377) no longer decides the result.
    expect(
      releaseSheetState({ height: 377, snaps: SNAPS, velocity: 0.8 }),
    ).toBe('half');
    expect(
      releaseSheetState({ height: 377.4, snaps: SNAPS, velocity: 0.8 }),
    ).toBe('half');
    expect(
      releaseSheetState({ height: 378.4, snaps: SNAPS, velocity: 0.8 }),
    ).toBe('half');
    expect(
      releaseSheetState({ height: 380.5, snaps: SNAPS, velocity: 0.8 }),
    ).toBe('full');
    // A drag from half that reversed below its start, then flicked up,
    // settles at half, not one step past the pre-drag state.
    expect(
      releaseSheetState({ height: 250, snaps: SNAPS, velocity: 0.9 }),
    ).toBe('half');
    expect(
      releaseSheetState({ height: 480, snaps: SNAPS, velocity: -0.9 }),
    ).toBe('half');
  });

  it('equals one step from the pre-drag state while the drag has not passed a snap', () => {
    const cases = [
      { from: 'peek', height: 200, velocity: 0.8 },
      { from: 'half', height: 450, velocity: 0.8 },
      { from: 'full', height: 500, velocity: -0.8 },
      { from: 'half', height: 300, velocity: -0.8 },
    ] as const;
    for (const { from, height, velocity } of cases) {
      expect(releaseSheetState({ height, snaps: SNAPS, velocity })).toBe(
        stepSheetState(from, velocity > 0 ? 1 : -1),
      );
    }
  });

  it('projects a slow release 120 ms ahead and snaps to the nearest state', () => {
    expect(
      releaseSheetState({
        height: 300,
        snaps: SNAPS,
        velocity: 0.1,
      }),
    ).toBe('half');
    expect(
      releaseSheetState({
        height: 200,
        snaps: SNAPS,
        velocity: -0.4,
      }),
    ).toBe('peek');
    expect(
      releaseSheetState({
        height: 470,
        snaps: SNAPS,
        velocity: 0.4,
      }),
    ).toBe('full');
    expect(
      releaseSheetState({
        height: 430,
        snaps: SNAPS,
        velocity: 0,
      }),
    ).toBe('half');
  });

  it('clamps travel between peek and full with no rubber band', () => {
    expect(clampSheetHeight(10, SNAPS)).toBe(78);
    expect(clampSheetHeight(900, SNAPS)).toBe(589);
    expect(clampSheetHeight(400, SNAPS)).toBe(400);
    expect(nearestSheetState(484, SNAPS)).toBe('half');
  });

  it('measures release velocity over the last 100 ms', () => {
    const steady = new VelocityTracker();
    steady.add(78, 0);
    steady.add(178, 100);
    expect(steady.velocity(100)).toBe(1);
    const stale = new VelocityTracker();
    stale.add(78, 0);
    stale.add(100, 50);
    stale.add(110, 300);
    expect(stale.velocity(300)).toBeCloseTo(10 / 250, 6);
    const burst = new VelocityTracker();
    burst.add(78, 10);
    burst.add(300, 10);
    expect(burst.velocity(10)).toBe(222);
    expect(new VelocityTracker().velocity(0)).toBe(0);
  });

  it('holds the last height until release, so nudge, hold, release is no flick', () => {
    const nudge = new VelocityTracker();
    nudge.add(379, 0);
    nudge.add(419, 40);
    expect(nudge.velocity(40)).toBe(1);
    expect(nudge.velocity(90)).toBeCloseTo(40 / 90, 6);
    expect(nudge.velocity(120)).toBeCloseTo(0.2, 6);
    expect(nudge.velocity(1040)).toBe(0);
    expect(
      releaseSheetState({
        height: 419,
        snaps: SNAPS,
        velocity: nudge.velocity(1040),
      }),
    ).toBe('half');
    const late = new VelocityTracker();
    late.add(78, 0);
    late.add(178, 100);
    expect(late.velocity(108)).toBeCloseTo(0.92, 6);
    expect(late.velocity(50)).toBe(1);
  });
});
