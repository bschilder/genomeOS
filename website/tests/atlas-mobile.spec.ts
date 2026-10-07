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
