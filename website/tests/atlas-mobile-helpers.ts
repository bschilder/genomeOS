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

/** True when data credit, Cesium credits and legend stack upward from the active sheet's top edge. */
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
    const stack = [
      '.atlas-data-credit',
      '.atlas-scene .cesium-viewer-bottom',
      '.atlas-legend',
    ]
      .map(visible)
      .filter((rect): rect is DOMRect => rect !== null);
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

/** Taps near the globe centre (as the desktop picking test clicks) until an inspector opens. */
export async function tapSelectNearCenter(page: Page): Promise<void> {
  const inspector = page.locator('.atlas-inspector');
  const centre = await centreOf(page.locator('.atlas-scene canvas').first());
  for (const [dx, dy] of CENTRE_OFFSETS) {
    await page.touchscreen.tap(centre.x + dx, centre.y + dy);
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
