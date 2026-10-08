/**
 * Site-header geometry for Atlas picker placement (mobile sheets design
 * 2026-10-07 §A.1.2): pickers open a gutter below the real header instead of
 * at hard-coded pixel offsets.
 */

export const PICKER_GUTTER_PX = 8;

export function siteHeaderBottom(root: ParentNode = document): number {
  return (
    root.querySelector('[data-site-header]')?.getBoundingClientRect().bottom ??
    0
  );
}

export function clampPickerTop(
  anchorTop: number,
  headerBottom: number,
  maxOffset: number,
): number {
  const lowest = headerBottom + PICKER_GUTTER_PX;
  return Math.max(lowest, Math.min(anchorTop, headerBottom + maxOffset));
}
