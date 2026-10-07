import { expect, test } from '@playwright/test';

import { installAtlasBrowserFixture } from './atlas-browser-fixture';
import {
  controlsSheet,
  dockedStackInOrder,
  PHONE_PROFILES,
  setSheetState,
  sheetGeometry,
  skipUnlessProject,
  waitForAtlasReady,
} from './atlas-mobile-helpers';
import { topLevelRoutes } from './site-routes';

test.beforeEach(async ({ page }) => installAtlasBrowserFixture(page));
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

for (const phone of PHONE_PROFILES) {
  test.describe(`${phone.name} phone`, () => {
    test.use(phone.use);
    test.beforeEach(({}, testInfo) =>
      skipUnlessProject(testInfo, 'mobile-chromium'),
    );

    for (const route of topLevelRoutes) {
      test(`${route} fits the phone width without zooming out`, async ({
        page,
      }) => {
        await page.goto(route);
        if (route === '/app/') await waitForAtlasReady(page);
        const fit = await page.evaluate(() => ({
          clientWidth: document.documentElement.clientWidth,
          scale: window.visualViewport?.scale ?? 1,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
        expect(fit.scale).toBe(1);
      });
    }

    test('the Atlas header keeps the status chip beside a 44 px menu', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const header = await page.evaluate(() => {
        const inner = document.querySelector('.site-header__inner')!;
        const chip = document.querySelector(
          '.atlas-navbar-status-slot .atlas-status',
        )!;
        const label = chip.querySelector('.atlas-status__copy strong')!;
        const menu = document
          .querySelector('.mobile-nav summary')!
          .getBoundingClientRect();
        return {
          chipRight: chip.getBoundingClientRect().right,
          clientWidth: inner.clientWidth,
          label: label.textContent,
          labelOverflow: getComputedStyle(label).textOverflow,
          menuHeight: menu.height,
          menuLeft: menu.left,
          menuWidth: menu.width,
          scrollWidth: inner.scrollWidth,
          wordmarkFont: getComputedStyle(document.querySelector('.wordmark')!)
            .fontFamily,
        };
      });
      expect(header.scrollWidth).toBeLessThanOrEqual(header.clientWidth);
      expect(header.chipRight).toBeLessThanOrEqual(header.menuLeft);
      expect(header.menuWidth).toBeGreaterThanOrEqual(44);
      expect(header.menuHeight).toBeGreaterThanOrEqual(44);
      expect(header.label).toBe('Atlas ready');
      expect(header.labelOverflow).toBe('ellipsis');
      expect(header.wordmarkFont).toContain('Raleway');
      await expect(page.locator('.mobile-nav summary')).toHaveAccessibleName(
        'Menu',
      );
    });

    test('Atlas status detail stays in the live region while visually hidden', async ({
      page,
    }) => {
      await page.goto('/app/', { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(
        () => {
          const detail = document.querySelector(
            '[data-atlas-status-slot] [role="status"] .atlas-status__copy small',
          );
          if (!detail) return false;
          const style = getComputedStyle(detail);
          return (
            style.display !== 'none' &&
            style.position === 'absolute' &&
            detail.getBoundingClientRect().width <= 1
          );
        },
        null,
        { polling: 'raf', timeout: 30_000 },
      );
    });

    test('/app/ fills the phone below the header without vertical scroll', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const shell = await page.evaluate(() => ({
        clientHeight: document.documentElement.clientHeight,
        explorerBottom: document
          .querySelector('.atlas-explorer')!
          .getBoundingClientRect().bottom,
        innerHeight: window.innerHeight,
        scrollHeight: document.documentElement.scrollHeight,
      }));
      expect(shell.scrollHeight).toBeLessThanOrEqual(shell.clientHeight);
      expect(
        Math.abs(shell.explorerBottom - shell.innerHeight),
      ).toBeLessThanOrEqual(0.5);
    });

    test('controls sheet cycles by tap and keyboard with named states', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(handle).toHaveAccessibleName('Explorer controls, peek');
      await expect(handle).toHaveAttribute('aria-expanded', 'false');
      const bodyId = await handle.getAttribute('aria-controls');
      expect(bodyId).toBeTruthy();
      await expect(page.locator(`[id="${bodyId}"]`)).toHaveClass(
        /atlas-sheet__body/,
      );

      await handle.tap();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
      await expect(handle).toHaveAccessibleName(
        'Explorer controls, half height',
      );
      await expect(handle).toHaveAttribute('aria-expanded', 'true');

      await handle.focus();
      await page.keyboard.press('Enter');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'full');
      await expect(handle).toHaveAccessibleName(
        'Explorer controls, full height',
      );
      await expect(handle).toHaveAttribute('aria-expanded', 'true');
      await expect(handle).toBeFocused();

      await page.keyboard.press('Enter');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(handle).toHaveAttribute('aria-expanded', 'false');
      await expect(handle).toBeFocused();
      await page.keyboard.press('Space');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');

      // Space straight after a touch tap advances exactly once: Chromium still
      // dispatches a native click on Space keyup while the tapped button is
      // :active, and onKeyUp cancels it (a second advance would land on 'half').
      await handle.tap();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'full');
      await handle.focus();
      await page.keyboard.press('Space');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
    });

    test('peek keeps the globe open and the sheet body inert', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      await expect
        .poll(async () => {
          const geometry = await sheetGeometry(page);
          return (
            geometry.sheetHeight >= 56 &&
            geometry.sheetHeight <= geometry.explorerHeight * 0.18 &&
            Math.abs(
              geometry.sheetTop +
                geometry.sheetHeight -
                geometry.explorerBottom,
            ) <= 1
          );
        })
        .toBe(true);
      await expect(sheet.locator('.atlas-sheet__body')).toHaveAttribute(
        'inert',
        '',
      );
      const summary = sheet.locator('.atlas-sheet__summary');
      await expect(summary).toHaveText('HbS (rs334) · Posterior estimate');
      await expect(
        summary.locator(
          'a, button, input, select, textarea, details, [tabindex]',
        ),
      ).toHaveCount(0);

      await sheet.locator('.atlas-sheet__handle').focus();
      let leftSheet = false;
      for (let press = 0; press < 3; press += 1) {
        await page.keyboard.press('Tab');
        const focus = await page.evaluate(() => ({
          inBody: Boolean(
            document.activeElement?.closest('.atlas-sheet__body'),
          ),
          inSheet: Boolean(
            document.activeElement?.closest('aside.atlas-controls'),
          ),
        }));
        expect(focus.inBody).toBe(false);
        if (!focus.inSheet) leftSheet = true;
      }
      expect(leftSheet).toBe(true);
    });

    test('half and full scroll the sheet body instead of moving it off-screen', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const body = sheet.locator('.atlas-sheet__body');

      await setSheetState(sheet, 'half');
      await expect
        .poll(async () => {
          const geometry = await sheetGeometry(page);
          return Math.abs(geometry.sheetHeight - geometry.explorerHeight / 2);
        })
        .toBeLessThanOrEqual(2);
      await expect(body).not.toHaveAttribute('inert', '');
      await expect(
        sheet.locator('details.atlas-control-sheet').filter({
          has: page.locator('summary', { hasText: /^Scientific layers$/ }),
        }),
      ).toHaveAttribute('open', '');

      await setSheetState(sheet, 'full');
      await expect
        .poll(async () => {
          const geometry = await sheetGeometry(page);
          return (
            geometry.sheetHeight > geometry.explorerHeight / 2 + 2 &&
            geometry.sheetHeight <= geometry.explorerHeight * 0.88 + 1
          );
        })
        .toBe(true);
      const scroll = await body.evaluate((element) => ({
        overflowY: getComputedStyle(element).overflowY,
        overscroll: getComputedStyle(element).overscrollBehaviorY,
      }));
      expect(scroll).toEqual({ overflowY: 'auto', overscroll: 'contain' });
      const keys = sheet.locator('.atlas-keyboard-help summary');
      await keys.scrollIntoViewIfNeeded();
      const [keysBox, bodyBox, geometry] = await Promise.all([
        keys.boundingBox(),
        body.boundingBox(),
        sheetGeometry(page),
      ]);
      expect(keysBox!.y).toBeGreaterThanOrEqual(bodyBox!.y - 1);
      expect(keysBox!.y + keysBox!.height).toBeLessThanOrEqual(
        bodyBox!.y + bodyBox!.height + 1,
      );
      expect(bodyBox!.y + bodyBox!.height).toBeLessThanOrEqual(
        geometry.explorerBottom + 1,
      );
    });

    test('entering peek moves focus to the handle before the body goes inert', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      await setSheetState(sheet, 'full');
      await sheet
        .locator('summary', { hasText: /^Scientific layers$/ })
        .focus();
      await page.keyboard.press('Escape');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(sheet.locator('.atlas-sheet__handle')).toBeFocused();
      await expect(sheet.locator('.atlas-sheet__body')).toHaveAttribute(
        'inert',
        '',
      );
    });

    test('the legend and credits dock above the sheet in every state', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      for (const state of ['peek', 'half', 'full'] as const) {
        await setSheetState(sheet, state);
        await expect.poll(() => dockedStackInOrder(page)).toBe(true);
      }
    });

    test('reduced motion snaps the sheet without animation', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const duration = await controlsSheet(page).evaluate((element) =>
        Number.parseFloat(getComputedStyle(element).transitionDuration),
      );
      expect(duration).toBeLessThan(0.001);
    });
  });
}

/*
 * /app/ sets viewport-fit=cover (§A.1.1), so a landscape iPhone lays the page
 * under the notch and the rounded corners and reports them as side insets.
 * Chromium takes the insets from a CDP override; these are Apple's landscape
 * values for each size (812 px is inside 52rem, 844 and 932 px are not).
 */
const LANDSCAPE_PHONES = [
  { inset: 50, viewport: { height: 375, width: 812 } },
  { inset: 47, viewport: { height: 390, width: 844 } },
  { inset: 59, viewport: { height: 430, width: 932 } },
] as const;

for (const phone of LANDSCAPE_PHONES) {
  const { height, width } = phone.viewport;
  test.describe(`${width}x${height} landscape phone`, () => {
    test.use({
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true,
      viewport: phone.viewport,
    });
    test.beforeEach(({}, testInfo) =>
      skipUnlessProject(testInfo, 'mobile-chromium'),
    );

    test('the Atlas header stays inside the side safe areas', async ({
      page,
    }) => {
      const cdp = await page.context().newCDPSession(page);
      await cdp.send('Emulation.setSafeAreaInsetsOverride', {
        insets: { bottom: 21, left: phone.inset, right: phone.inset, top: 0 },
      });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      await page.locator('.skip-link').focus();
      const header = await page.evaluate(() => {
        const box = (selector: string) =>
          document.querySelector(selector)!.getBoundingClientRect();
        const inner = document.querySelector('.site-header__inner')!;
        return {
          backgroundLeft: box('.site-header').left,
          backgroundRight: box('.site-header').right,
          clientWidth: document.documentElement.clientWidth,
          innerClientWidth: inner.clientWidth,
          innerScrollWidth: inner.scrollWidth,
          menuRight: box('.mobile-nav summary').right,
          skipLinkLeft: box('.skip-link').left,
          wordmarkLeft: box('.wordmark').left,
        };
      });
      const safeRight = header.clientWidth - phone.inset;
      // Soft, so one run names every element that sits under an inset.
      expect.soft(header.wordmarkLeft).toBeGreaterThanOrEqual(phone.inset);
      expect.soft(header.menuRight).toBeLessThanOrEqual(safeRight);
      expect.soft(header.skipLinkLeft).toBeGreaterThanOrEqual(phone.inset);
      expect(header.innerScrollWidth).toBeLessThanOrEqual(
        header.innerClientWidth,
      );
      // The header background still runs edge to edge under the insets.
      expect(header.backgroundLeft).toBe(0);
      expect(header.backgroundRight).toBe(header.clientWidth);
    });
  });
}
