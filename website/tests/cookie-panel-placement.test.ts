/** Where the cookie settings panel opens beside its icon (#422). */
import { describe, expect, it } from 'vitest';

import {
  PANEL_GAP_PX,
  VIEWPORT_GUTTER_PX,
  panelPlacement,
  type Box,
} from '../src/lib/cookie-panel-placement';

const box = (left: number, top: number, size = 30): Box => ({
  left,
  top,
  right: left + size,
  bottom: top + size,
});

describe('panelPlacement', () => {
  it('opens above the corner icon, right edges aligned', () => {
    const viewport = { width: 1440, height: 900 };
    const icon = box(1396, 856); // right 14, bottom 14
    expect(
      panelPlacement({
        anchor: icon,
        panel: { width: 320, height: 220 },
        viewport,
        headerBottom: 70,
      }),
    ).toEqual({
      side: 'above',
      right: 14,
      offset: 900 - 856 + PANEL_GAP_PX,
      maxHeight: 856 - PANEL_GAP_PX - (70 + PANEL_GAP_PX),
    });
  });

  it('never rises over the site header: its height is capped to the room above', () => {
    const placement = panelPlacement({
      anchor: box(330, 250, 24),
      panel: { width: 336, height: 400 },
      viewport: { width: 390, height: 844 },
      headerBottom: 87,
    });
    // More room below, so it opens there instead.
    expect(placement.side).toBe('below');
    expect(placement.offset).toBe(274 + PANEL_GAP_PX);
    expect(placement.maxHeight).toBe(
      844 - VIEWPORT_GUTTER_PX - (274 + PANEL_GAP_PX),
    );
    const above = panelPlacement({
      anchor: box(330, 600, 24),
      panel: { width: 336, height: 200 },
      viewport: { width: 390, height: 844 },
      headerBottom: 87,
    });
    expect(above.side).toBe('above');
    expect(above.maxHeight).toBe(600 - PANEL_GAP_PX - (87 + PANEL_GAP_PX));
  });

  it('keeps a viewport gutter on both sides', () => {
    // An icon flush with the right edge still leaves the gutter.
    expect(
      panelPlacement({
        anchor: box(380, 700, 10),
        panel: { width: 300, height: 100 },
        viewport: { width: 390, height: 844 },
      }).right,
    ).toBe(VIEWPORT_GUTTER_PX);
    // A panel as wide as the room left keeps the gutter on the left too.
    const placement = panelPlacement({
      anchor: box(320, 700, 24),
      panel: { width: 336, height: 100 },
      viewport: { width: 360, height: 780 },
    });
    expect(placement.right).toBe(VIEWPORT_GUTTER_PX);
    expect(360 - placement.right - 336).toBeGreaterThanOrEqual(
      VIEWPORT_GUTTER_PX,
    );
  });

  it('lines up with the left edge of an icon on the left half (the desktop Atlas corner)', () => {
    const placement = panelPlacement({
      anchor: box(18, 854, 28),
      panel: { width: 360, height: 200 },
      viewport: { width: 1440, height: 900 },
      headerBottom: 87,
    });
    expect(placement.side).toBe('above');
    // The panel's left edge is the icon's.
    expect(1440 - placement.right - 360).toBe(18);
  });

  it('never reports a negative height', () => {
    expect(
      panelPlacement({
        anchor: box(300, 5, 24),
        panel: { width: 200, height: 100 },
        viewport: { width: 320, height: 30 },
      }).maxHeight,
    ).toBeGreaterThanOrEqual(0);
  });
});
