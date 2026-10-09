/** Shared Playwright helpers for the Atlas phone layout (mobile sheets design 2026-10-07 §A.3). */

import {
  expect,
  test,
  type Locator,
  type Page,
  type TestInfo,
} from '@playwright/test';

export const PHONE_PROFILES = [
  { name: 'Pixel 7', use: {} },
  {
    name: '360x780',
    use: {
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true,
      viewport: { height: 780, width: 360 },
    },
  },
  {
    name: '390x844',
    use: {
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true,
      viewport: { height: 844, width: 390 },
    },
  },
] as const;

export function skipUnlessProject(
  testInfo: TestInfo,
  project: 'desktop-chromium' | 'mobile-chromium',
): void {
  test.skip(
    testInfo.project.name !== project,
    `runs only in the ${project} project`,
  );
}

export async function waitForAtlasReady(page: Page): Promise<void> {
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });
}

export type SheetStateName = 'peek' | 'half' | 'full';

export function controlsSheet(page: Page): Locator {
  return page.locator('aside.atlas-controls');
}

export async function setSheetState(
  sheet: Locator,
  state: SheetStateName,
): Promise<void> {
  const handle = sheet.locator('.atlas-sheet__handle');
  for (let press = 0; press < 3; press += 1) {
    const current = await sheet.getAttribute('data-sheet-state');
    if (current === state) return;
    await handle.click();
    await expect(sheet).not.toHaveAttribute('data-sheet-state', current ?? '');
  }
  await expect(sheet).toHaveAttribute('data-sheet-state', state);
}

/**
 * setSheetState by touch taps on the handle. Tests that pick on the globe use
 * it: Cesium reacts to where Playwright leaves the emulated mouse of a handle
 * click (over the globe once the sheet drops back), which a phone does not
 * have.
 */
export async function tapSheetState(
  sheet: Locator,
  state: SheetStateName,
): Promise<void> {
  const handle = sheet.locator('.atlas-sheet__handle');
  for (let tap = 0; tap < 3; tap += 1) {
    const current = await sheet.getAttribute('data-sheet-state');
    if (current === state) return;
    await handle.tap();
    await expect(sheet).not.toHaveAttribute('data-sheet-state', current ?? '');
  }
  await expect(sheet).toHaveAttribute('data-sheet-state', state);
}

/** Opens the phone controls sheet fully; a no-op for the always-open desktop dock. */
export async function expandExplorerSheet(page: Page): Promise<void> {
  const sheet = page.locator('aside.atlas-controls[data-sheet-state]');
  if ((await sheet.count()) === 0) return;
  await setSheetState(sheet, 'full');
}

export interface SheetGeometry {
  explorerBottom: number;
  explorerHeight: number;
  sheetHeight: number;
  sheetTop: number;
}

export async function sheetGeometry(
  page: Page,
  selector = 'aside.atlas-controls',
): Promise<SheetGeometry> {
  return page.evaluate((sheetSelector) => {
    const explorer = document
      .querySelector('.atlas-explorer')!
      .getBoundingClientRect();
    const sheet = document
      .querySelector(sheetSelector)!
      .getBoundingClientRect();
    return {
      explorerBottom: explorer.bottom,
      explorerHeight: explorer.height,
      sheetHeight: sheet.height,
      sheetTop: sheet.top,
    };
  }, selector);
}

/**
 * True when data credit, Cesium credits and legend are all shown and stack
 * upward from the active sheet's top edge; a collapsed strip is a failure.
 */
export async function dockedStackInOrder(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const visible = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 ? rect : null;
    };
    const sheet =
      visible('aside.atlas-controls:not([hidden])') ??
      visible('.atlas-right-rail[data-sheet-state]');
    if (!sheet) return false;
    const selectors = [
      '.atlas-data-credit',
      '.atlas-scene .cesium-viewer-bottom',
      '.atlas-legend',
    ];
    const stack = selectors
      .map(visible)
      .filter((rect): rect is DOMRect => rect !== null);
    if (stack.length < selectors.length) return false;
    let edge = sheet.top;
    for (const rect of stack) {
      if (rect.bottom > edge + 1) return false;
      edge = rect.top;
    }
    return true;
  });
}

export interface Point {
  x: number;
  y: number;
}

export interface TouchGesture {
  move(to: Point): Promise<void>;
  end(): Promise<void>;
}

/** One finger through Chrome's real input pipeline (CDP), so touch-action and pointer events behave as on a phone. */
export async function startTouch(page: Page, at: Point): Promise<TouchGesture> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent', {
    touchPoints: [{ id: 1, x: at.x, y: at.y }],
    type: 'touchStart',
  });
  return {
    async move(to) {
      await cdp.send('Input.dispatchTouchEvent', {
        touchPoints: [{ id: 1, x: to.x, y: to.y }],
        type: 'touchMove',
      });
    },
    async end() {
      await cdp.send('Input.dispatchTouchEvent', {
        touchPoints: [],
        type: 'touchEnd',
      });
      await cdp.detach();
    },
  };
}

export async function touchDrag(
  page: Page,
  from: Point,
  to: Point,
  steps = 8,
): Promise<void> {
  const gesture = await startTouch(page, from);
  for (let step = 1; step <= steps; step += 1) {
    await gesture.move({
      x: from.x + ((to.x - from.x) * step) / steps,
      y: from.y + ((to.y - from.y) * step) / steps,
    });
    await page.waitForTimeout(16);
  }
  await gesture.end();
}

export async function centreOf(locator: Locator): Promise<Point> {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 };
}

export const INSPECTOR_CAMERA = new URLSearchParams({
  heading: '0',
  height: '1000000',
  lat: '40.4407',
  lon: '-3.7201',
  pitch: '-90',
}).toString();

const CENTRE_OFFSETS = [
  [0, 0],
  [-18, 0],
  [18, 0],
  [0, -18],
  [0, 18],
  [-18, -18],
  [18, -18],
  [-18, 18],
  [18, 18],
] as const;

export function panelSheet(page: Page): Locator {
  return page.locator('.atlas-right-rail');
}

/** True when the point hit-tests to the Cesium canvas, not to a sheet or other chrome. */
async function canvasAt(page: Page, point: Point): Promise<boolean> {
  return page.evaluate(
    ({ x, y }) =>
      document.elementFromPoint(x, y)?.matches('.atlas-scene canvas') ?? false,
    point,
  );
}

/**
 * Taps near the globe centre (as the desktop picking test clicks) until an
 * inspector opens. A slow pick can open the panel sheet at half after its wait
 * timed out, so each retry first checks that no inspector is open and that its
 * point is still bare canvas; otherwise it would tap the new sheet's handle.
 */
export async function tapSelectNearCenter(page: Page): Promise<void> {
  const inspector = page.locator('.atlas-inspector');
  const centre = await centreOf(page.locator('.atlas-scene canvas').first());
  for (const [dx, dy] of CENTRE_OFFSETS) {
    if (await inspector.isVisible()) return;
    const point = { x: centre.x + dx, y: centre.y + dy };
    if (!(await canvasAt(page, point))) continue;
    await page.touchscreen.tap(point.x, point.y);
    const opened = await inspector
      .waitFor({ state: 'visible', timeout: 1_500 })
      .then(
        () => true,
        () => false,
      );
    if (opened) return;
  }
  await expect(inspector).toBeVisible();
}

/** 12 × 20 hit-test grid over the explorer: canvas fraction and misses in the central region. */
export async function canvasCoverage(
  page: Page,
): Promise<{ centreMisses: number; fraction: number }> {
  return page.evaluate(() => {
    const explorer = document
      .querySelector('.atlas-explorer')!
      .getBoundingClientRect();
    let canvas = 0;
    let centreMisses = 0;
    for (let row = 0; row < 20; row += 1) {
      for (let column = 0; column < 12; column += 1) {
        const x = explorer.left + ((column + 0.5) * explorer.width) / 12;
        const y = explorer.top + ((row + 0.5) * explorer.height) / 20;
        const hit = document.elementFromPoint(x, y);
        const onCanvas =
          hit instanceof HTMLCanvasElement &&
          hit.closest('.atlas-scene') !== null;
        if (onCanvas) canvas += 1;
        const central =
          x >= explorer.left + explorer.width * 0.2 &&
          x <= explorer.left + explorer.width * 0.8 &&
          y >= explorer.top + explorer.height * 0.3 &&
          y <= explorer.top + explorer.height * 0.7;
        if (central && !onCanvas) centreMisses += 1;
      }
    }
    return { centreMisses, fraction: canvas / 240 };
  });
}

/** Docked or status elements that reach into the central 60 % × 40 % of the explorer. */
export async function dockedOutsideCentre(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const explorer = document
      .querySelector('.atlas-explorer')!
      .getBoundingClientRect();
    const centre = {
      bottom: explorer.top + explorer.height * 0.7,
      left: explorer.left + explorer.width * 0.2,
      right: explorer.left + explorer.width * 0.8,
      top: explorer.top + explorer.height * 0.3,
    };
    return [
      '.atlas-legend',
      '.atlas-scene .cesium-viewer-bottom',
      '.atlas-data-credit',
      '.atlas-status-stack',
    ].filter((selector) => {
      const element = document.querySelector(selector);
      if (!element) return false;
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      return (
        rect.left < centre.right &&
        rect.right > centre.left &&
        rect.top < centre.bottom &&
        rect.bottom > centre.top
      );
    });
  });
}

/**
 * Credit logos and links that are missing, off-screen or covered by another
 * element. The ion logo, a map credit link and the data credit link must be
 * shown (§A.1.7), so a collapsed credit block fails instead of leaving
 * nothing to check.
 */
export async function uncoveredCredits(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = (element: Element) => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const failures: string[] = [];
    for (const [label, selector] of [
      ['Cesium ion logo', '.atlas-scene .cesium-credit-logoContainer img'],
      [
        'map credit link',
        '.atlas-scene .cesium-credit-textContainer a, .atlas-scene .cesium-credit-expand-link',
      ],
      ['data credit link', '.atlas-data-credit a'],
    ] as const) {
      if (!Array.from(document.querySelectorAll(selector)).some(shown))
        failures.push(`${label} not shown`);
    }
    const targets = [
      ...document.querySelectorAll<HTMLElement>(
        '.atlas-scene .cesium-credit-logoContainer img, .atlas-scene .cesium-viewer-bottom a, .atlas-data-credit a',
      ),
    ];
    for (const target of targets) {
      const rect = target.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      const label =
        target.textContent?.trim() ||
        target.getAttribute('alt') ||
        target.tagName;
      const inside =
        rect.left >= 0 &&
        rect.top >= 0 &&
        rect.right <= window.innerWidth &&
        rect.bottom <= window.innerHeight;
      // The credit block wraps by design (§A.1.7), so an inline link can split
      // across lines and its bounding-box centre can fall on the canvas. Hit-test
      // the centre of every non-empty line fragment instead.
      const fragments = Array.from(target.getClientRects()).filter(
        (fragment) => fragment.width >= 1 && fragment.height >= 1,
      );
      const reachable =
        fragments.length > 0 &&
        fragments.every((fragment) => {
          const hit = document.elementFromPoint(
            fragment.left + fragment.width / 2,
            fragment.top + fragment.height / 2,
          );
          return hit !== null && (hit === target || target.contains(hit));
        });
      if (!inside || !reachable) failures.push(label);
    }
    return failures;
  });
}

/**
 * Whether the active sheet clears the top chrome by 8 px and which docked
 * strips overlap it. Only shown parts count: a short explorer hides the top
 * chrome under a full sheet and the strips above peek (visibility: hidden).
 */
export async function topChromeClearance(
  page: Page,
): Promise<{ gap: boolean; intersections: string[] }> {
  return page.evaluate(() => {
    const shown = (element: Element) => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 &&
        rect.height > 0 &&
        getComputedStyle(element).visibility !== 'hidden'
        ? rect
        : null;
    };
    const rectsOf = (selector: string) =>
      Array.from(document.querySelectorAll(selector))
        .map(shown)
        .filter((rect): rect is DOMRect => rect !== null);
    const explorerTop = document
      .querySelector('.atlas-explorer')!
      .getBoundingClientRect().top;
    const chrome = rectsOf(
      '.atlas-warning-banner, .atlas-top-slot > :not(h1), .atlas-status-stack, .atlas-view-notice',
    );
    const chromeBottom = Math.max(
      0,
      ...chrome.map((rect) => rect.bottom - explorerTop),
    );
    const sheet =
      rectsOf('aside.atlas-controls:not([hidden])')[0] ??
      rectsOf('.atlas-right-rail[data-sheet-state]')[0] ??
      null;
    const intersections = [
      '.atlas-legend',
      '.atlas-scene .cesium-viewer-bottom',
      '.atlas-data-credit',
    ].filter((selector) =>
      rectsOf(selector).some((rect) =>
        chrome.some(
          (other) =>
            rect.left < other.right &&
            rect.right > other.left &&
            rect.top < other.bottom &&
            rect.bottom > other.top,
        ),
      ),
    );
    return {
      gap: sheet !== null && sheet.top - explorerTop >= chromeBottom + 8 - 0.5,
      intersections,
    };
  });
}

/**
 * Puts the legend in its cold-reveal state as AtlasLegend renders it
 * (fast-load design §B.6.8): the attribute on the aside and the status pill
 * after the mode pill, markup that tests/atlas-legend.test.ts pins. The
 * explorer shows that state only until the cold reveal commits, so this holds
 * it for checks across viewports; `recordLegendLoading` checks the real one.
 */
export async function markLegendLoading(page: Page): Promise<void> {
  await page.locator('.atlas-legend').evaluate((legend) => {
    legend.setAttribute('data-atlas-legend-loading', 'true');
    const pill = document.createElement('span');
    pill.className = 'atlas-legend__mode atlas-legend__loading';
    pill.setAttribute('role', 'status');
    pill.textContent = 'Loading map…';
    legend.querySelector('.atlas-legend__mode')!.after(pill);
  });
}

export interface LegendRow {
  /** The info trigger's top is above the metric label's bottom: one line, not wrapped. */
  infoBesideLabel: boolean;
  /** The info trigger shares the ramp's row. */
  infoInRow: boolean;
  /** How far the legend's content overflows its box, in CSS px. */
  overflow: number;
  rampWidth: number;
  /** Top of the [label | ramp | … | info] row in the viewport. */
  rowTop: number;
  /** Where the loading status sits, when the legend shows one. */
  status: { aboveRow: boolean; insideLegend: boolean } | null;
}

/** Measures the legend in the page; serialised there, so it uses nothing outside itself. */
function measureLegendRow(legend: Element): LegendRow {
  const box = (selector: string) =>
    legend.querySelector(selector)!.getBoundingClientRect();
  const outer = legend.getBoundingClientRect();
  const label = box('.atlas-legend__compact > strong');
  const scale = box('.atlas-color-scale');
  const info = box('.atlas-legend__info summary');
  const rowTop = Math.min(label.top, scale.top, info.top);
  const status = legend
    .querySelector('.atlas-legend__loading')
    ?.getBoundingClientRect();
  return {
    infoBesideLabel: info.top < label.bottom,
    infoInRow: info.top < scale.bottom && info.bottom > scale.top,
    overflow: legend.scrollWidth - legend.clientWidth,
    rampWidth: box('.atlas-color-scale i').width,
    rowTop,
    status: status
      ? {
          aboveRow: status.bottom <= rowTop + 0.5,
          insideLegend:
            status.left >= outer.left - 0.5 &&
            status.right <= outer.right + 0.5 &&
            status.top >= outer.top - 0.5 &&
            status.bottom <= outer.bottom + 0.5,
        }
      : null,
  };
}

/** The legend's one row of label, ramp and info trigger, and its loading status. */
export async function legendRow(page: Page): Promise<LegendRow> {
  return page.locator('.atlas-legend').evaluate(measureLegendRow);
}

export interface LegendLoadingRecord extends LegendRow {
  /** The status element is laid out (not `display: none` or hidden). */
  statusShown: boolean;
  statusText: string | null;
}

/**
 * Call before navigating. Records the legend the moment the explorer first
 * renders it in its cold-reveal state (fast-load design §B.6.8), between the
 * first surface chunk and the commit, a window too short to poll for.
 */
export async function recordLegendLoading(page: Page): Promise<void> {
  await page.addInitScript(`(() => {
    const measure = ${measureLegendRow.toString()};
    const observer = new MutationObserver(() => {
      const legend = document.querySelector(
        '.atlas-legend[data-atlas-legend-loading="true"]',
      );
      if (!legend) return;
      observer.disconnect();
      const status = legend.querySelector('[role="status"]');
      const style = status ? getComputedStyle(status) : null;
      window.atlasLegendLoading = {
        ...measure(legend),
        statusShown: Boolean(
          style && style.display !== 'none' && style.visibility !== 'hidden',
        ),
        statusText: status ? status.textContent : null,
      };
    });
    observer.observe(document, {
      attributeFilter: ['data-atlas-legend-loading'],
      attributes: true,
      childList: true,
      subtree: true,
    });
  })();`);
}

/** What `recordLegendLoading` saw, or null if the legend never showed its loading state. */
export async function recordedLegendLoading(
  page: Page,
): Promise<LegendLoadingRecord | null> {
  return page.evaluate(
    () =>
      (window as unknown as { atlasLegendLoading?: LegendLoadingRecord })
        .atlasLegendLoading ?? null,
  );
}
