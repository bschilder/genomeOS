/**
 * Where the cookie settings panel opens (#422): beside the icon that opened it, which is the
 * fixed corner icon on most pages and the icon docked in the Atlas on /app/
 * (AtlasCookieSettings.tsx). Pure, so it unit-tests without a DOM.
 *
 * The panel lines up with the icon's outer edge (its right edge for an icon on the right half of
 * the viewport, its left edge for one on the left, like the desktop Atlas's bottom-left icon) and
 * opens above it when it fits there whole, or when there is more room above than below; otherwise
 * below. It never rises over the site header, never leaves a viewport gutter, and its height is
 * capped to the room on the chosen side (it scrolls within it).
 */

/** The gap between the icon and the panel. */
export const PANEL_GAP_PX = 8;
/** The panel keeps at least this far from every viewport edge. */
export const VIEWPORT_GUTTER_PX = 12;

export interface Box {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface PanelPlacement {
  side: 'above' | 'below';
  /** CSS `right`, from the viewport's right edge. */
  right: number;
  /** CSS `bottom` for a panel above the icon, or `top` for one below it. */
  offset: number;
  maxHeight: number;
}

export function panelPlacement({
  anchor,
  panel,
  viewport,
  headerBottom = 0,
}: {
  anchor: Box;
  panel: { width: number; height: number };
  viewport: { width: number; height: number };
  /** The bottom edge of the site header, which the panel never covers. */
  headerBottom?: number;
}): PanelPlacement {
  const onLeft = anchor.left + anchor.right < viewport.width;
  const aligned = onLeft
    ? viewport.width - anchor.left - panel.width
    : viewport.width - anchor.right;
  const right = Math.max(
    VIEWPORT_GUTTER_PX,
    Math.min(aligned, viewport.width - VIEWPORT_GUTTER_PX - panel.width),
  );
  const ceiling = Math.max(VIEWPORT_GUTTER_PX, headerBottom + PANEL_GAP_PX);
  const above = anchor.top - PANEL_GAP_PX - ceiling;
  const below =
    viewport.height - VIEWPORT_GUTTER_PX - (anchor.bottom + PANEL_GAP_PX);
  if (above >= panel.height || above >= below)
    return {
      side: 'above',
      right,
      offset: viewport.height - anchor.top + PANEL_GAP_PX,
      maxHeight: Math.max(0, Math.floor(above)),
    };
  return {
    side: 'below',
    right,
    offset: anchor.bottom + PANEL_GAP_PX,
    maxHeight: Math.max(0, Math.floor(below)),
  };
}
