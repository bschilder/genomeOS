import { expect, test } from '@playwright/test';

import { installAtlasBrowserFixture } from './atlas-browser-fixture';
import {
  PHONE_PROFILES,
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
