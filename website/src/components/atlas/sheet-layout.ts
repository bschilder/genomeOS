/**
 * DOM measurements behind the Atlas bottom sheets (mobile sheets design
 * 2026-10-07 §A.1.5 full-height cap, §A.1.7 docking and the legend popover's
 * room). Cesium-free: it reads the Cesium credit container only as a DOM
 * node.
 */

import { TOP_CHROME_GAP_PX } from './sheet-geometry';

const TOP_CHROME =
  '.atlas-warning-banner, .atlas-top-slot, .atlas-status-stack, .atlas-view-notice';
const LEGEND = '.atlas-legend';
const CESIUM_CREDITS = '.atlas-scene .cesium-viewer-bottom';
const DATA_CREDIT = '.atlas-data-credit';

export const PEEK_GAP_PX = 8;

function heightOf(root: ParentNode, selector: string): number {
  return (
    root.querySelector<HTMLElement>(selector)?.getBoundingClientRect().height ??
    0
  );
}

/** Largest bottom edge of the top chrome, relative to the explorer's top. */
export function topChromeBottom(explorer: HTMLElement): number {
  const top = explorer.getBoundingClientRect().top;
  let bottom = 0;
  for (const element of explorer.querySelectorAll<HTMLElement>(TOP_CHROME)) {
    const rect = element.getBoundingClientRect();
    if (rect.height > 0) bottom = Math.max(bottom, rect.bottom - top);
  }
  return bottom;
}

/** Legend strip plus credit block, the height docked above the active sheet. */
export function dockedHeight(explorer: HTMLElement): number {
  return (
    heightOf(explorer, LEGEND) +
    heightOf(explorer, CESIUM_CREDITS) +
    heightOf(explorer, DATA_CREDIT)
  );
}

/** Publishes the credit heights the docking CSS stacks with. */
export function writeDockedStack(explorer: HTMLElement): void {
  const data = heightOf(explorer, DATA_CREDIT);
  explorer.style.setProperty('--atlas-data-credit-height', `${data}px`);
  explorer.style.setProperty(
    '--atlas-credit-height',
    `${data + heightOf(explorer, CESIUM_CREDITS)}px`,
  );
}

/**
 * Places the phone legend popover (§A.1.7) inside the explorer: above the
 * strip when it fits whole there, otherwise on the side with more room, which
 * over a half or full sheet is below, across the sheet. The chosen side's
 * room, between the top chrome (plus its 8 px gap) and the explorer's bottom
 * less 8 px, caps the popover's height; it scrolls within it.
 */
export function placeLegendPopover(details: HTMLElement): void {
  const explorer = details.closest<HTMLElement>('.atlas-explorer');
  const popover = details.querySelector<HTMLElement>(':scope > div');
  if (!explorer || !popover) return;
  const bounds = explorer.getBoundingClientRect();
  const info = details.getBoundingClientRect();
  const gap =
    0.7 *
    Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
  const top = bounds.top + topChromeBottom(explorer) + TOP_CHROME_GAP_PX;
  const above = info.top - gap - top;
  const below = bounds.bottom - TOP_CHROME_GAP_PX - (info.bottom + gap);
  const placement =
    above >= popover.scrollHeight || above >= below ? 'above' : 'below';
  details.dataset.placement = placement;
  details.style.setProperty(
    '--atlas-legend-room',
    `${Math.max(0, Math.floor(placement === 'above' ? above : below))}px`,
  );
}

/**
 * Visible height of a sheet at peek: down to its last [data-sheet-peek] row,
 * then the sheet's bottom padding (the safe-area inset), at least PEEK_GAP_PX.
 * A home-indicator inset already spaces the last row from the screen edge, so
 * it absorbs the gap instead of adding to it, and the peek band plus the
 * docked strips above it stay clear of the globe's centre (§A.1.3).
 */
export function peekHeight(sheet: HTMLElement): number {
  const top = sheet.getBoundingClientRect().top;
  let bottom = 0;
  for (const element of sheet.querySelectorAll<HTMLElement>(
    '[data-sheet-peek]',
  )) {
    bottom = Math.max(bottom, element.getBoundingClientRect().bottom - top);
  }
  const padding = Number.parseFloat(getComputedStyle(sheet).paddingBottom);
  return bottom + Math.max(PEEK_GAP_PX, Number.isFinite(padding) ? padding : 0);
}

/** Calls onChange (once per frame) when the explorer, chrome, docked block or peek rows change. */
export function observeSheetLayout(
  explorer: HTMLElement,
  onChange: () => void,
): () => void {
  let frame = 0;
  const schedule = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      onChange();
    });
  };
  const resize = new ResizeObserver(schedule);
  const observeAll = () => {
    resize.disconnect();
    resize.observe(explorer);
    for (const element of explorer.querySelectorAll(
      `${TOP_CHROME}, ${LEGEND}, ${CESIUM_CREDITS}, ${DATA_CREDIT}, [data-sheet-peek]`,
    )) {
      resize.observe(element);
    }
  };
  const mutation = new MutationObserver(() => {
    observeAll();
    schedule();
  });
  mutation.observe(explorer, { childList: true, subtree: true });
  observeAll();
  return () => {
    cancelAnimationFrame(frame);
    resize.disconnect();
    mutation.disconnect();
  };
}
