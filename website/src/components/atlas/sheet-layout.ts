/**
 * DOM measurements behind the Atlas bottom sheets (mobile sheets design
 * 2026-10-07 §A.1.5 full-height cap, §A.1.7 docking). Cesium-free: it reads
 * the Cesium credit container only as a DOM node.
 */

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
