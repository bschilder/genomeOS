/**
 * Google Analytics 4 and the cookie control (#422; consent model refined by the owner on
 * 2026-10-10): opt-out by default, Global Privacy Control honoured, opt-in in EEA, UK and Swiss
 * time zones, and a small cookie icon on every page.
 *
 * `npm run test:e2e` builds with the placeholder Measurement ID G-TEST123, and the Atlas browser
 * fixture answers gtag.js with an empty stub, so every gtag call stays in the page's
 * window.dataLayer and none reaches Google.
 */
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';

import { installAtlasBrowserFixture } from './atlas-browser-fixture';
import {
  PHONE_PROFILES,
  controlsSheet,
  setSheetState,
  waitForAtlasReady,
} from './atlas-mobile-helpers';

const MEASUREMENT_ID = 'G-TEST123';
const LOADER = `<script async src="https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}"></script>`;
const STORAGE_KEY = 'genomeos-analytics-consent';
const BERLIN = 'Europe/Berlin';
const NEW_YORK = 'America/New_York';
const dist = path.resolve(import.meta.dirname, '../dist');

test.beforeEach(async ({ page }) => installAtlasBrowserFixture(page));
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

function htmlFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return htmlFiles(target);
    return entry.name.endsWith('.html') ? [target] : [];
  });
}

/** The page's gtag calls, oldest first, as plain arrays. */
async function gtagCalls(page: Page): Promise<unknown[][]> {
  return page.evaluate(() =>
    (
      ((window as unknown as { dataLayer?: IArguments[] }).dataLayer ??
        []) as IArguments[]
    ).map((call) => JSON.parse(JSON.stringify(Array.from(call))) as unknown[]),
  );
}

/** The analytics_storage of each consent update, oldest first. */
async function consentUpdates(page: Page): Promise<unknown[]> {
  return (await gtagCalls(page))
    .filter(([command, action]) => command === 'consent' && action === 'update')
    .map(
      (call) => (call[2] as { analytics_storage?: unknown }).analytics_storage,
    );
}

/** Whether every consent update came before the config. */
async function updatesBeforeConfig(page: Page): Promise<boolean> {
  const calls = await gtagCalls(page);
  const config = calls.findIndex(([command]) => command === 'config');
  const updates = calls
    .map(([command, action], index) =>
      command === 'consent' && action === 'update' ? index : -1,
    )
    .filter((index) => index >= 0);
  return config >= 0 && updates.every((index) => index < config);
}

async function storedChoice(page: Page): Promise<string | null> {
  return page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY);
}

function panel(page: Page): Locator {
  return page.getByRole('region', { name: 'Cookie settings' });
}

function cornerIcon(page: Page): Locator {
  return page.locator('[data-cookie-toggle]');
}

function analyticsSwitch(page: Page): Locator {
  return panel(page).getByRole('switch', { name: 'Analytics cookies' });
}

function footerSettings(page: Page): Locator {
  return page
    .getByRole('navigation', { name: 'Site policies' })
    .getByRole('button', { name: 'Cookie settings' });
}

/** Wait for the cookie control's module script, which marks the control with the consent state. */
async function waitForCookieControl(page: Page): Promise<void> {
  await page.locator('[data-cookie-control][data-consent]').waitFor({
    state: 'attached',
  });
}

/** A browser that sends Global Privacy Control (`navigator.globalPrivacyControl === true`). */
async function sendGlobalPrivacyControl(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {
      configurable: true,
      get: () => true,
    });
  });
}

async function seriousAxeViolations(page: Page): Promise<unknown[]> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations.filter(({ impact }) =>
    ['serious', 'critical'].includes(impact ?? ''),
  );
}

interface Clearance {
  hit: boolean;
  inViewport: boolean;
  overlaps: string[];
  size: { height: number; width: number };
}

/**
 * The shown cookie icon's clearance: whether a pointer at its centre reaches it, whether it lies
 * inside the viewport, and which of the given elements' boxes it intersects.
 */
async function iconClearance(
  icon: Locator,
  others: readonly string[],
): Promise<Clearance> {
  return icon.evaluate((element, selectors) => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(
      rect.left + rect.width / 2,
      rect.top + rect.height / 2,
    );
    const overlaps = selectors.filter((selector) =>
      Array.from(document.querySelectorAll(selector)).some((other) => {
        if (other.contains(element)) return false;
        const box = other.getBoundingClientRect();
        return (
          box.width > 0 &&
          box.height > 0 &&
          rect.left < box.right &&
          rect.right > box.left &&
          rect.top < box.bottom &&
          rect.bottom > box.top
        );
      }),
    );
    return {
      hit: hit !== null && element.contains(hit),
      inViewport:
        rect.left >= 0 &&
        rect.top >= 0 &&
        rect.right <= window.innerWidth &&
        rect.bottom <= window.innerHeight,
      overlaps,
      size: { height: rect.height, width: rect.width },
    };
  }, others);
}

test.describe('analytics build', { tag: '@desktop-chromium' }, () => {
  test('every page loads gtag once, with the consent defaults and updates before the config', () => {
    const pages = htmlFiles(dist);
    const app = readFileSync(path.join(dist, 'app/index.html'), 'utf8');
    if (!app.includes(LOADER))
      throw new Error(
        'dist/ was built without the placeholder Measurement ID. Run `npm run test:e2e`, which builds with PUBLIC_GA_MEASUREMENT_ID=G-TEST123.',
      );
    const routes = pages.map((file) => path.relative(dist, file));
    for (const route of [
      'index.html',
      'app/index.html',
      'app/polygon/index.html',
      'docs/index.html',
      'docs/deployment/index.html',
      'privacy/index.html',
      '404.html',
    ])
      expect(routes).toContain(route);
    for (const file of pages) {
      const route = path.relative(dist, file);
      const html = readFileSync(file, 'utf8');
      expect(html.split('googletagmanager.com').length - 1, route).toBe(1);
      expect(html.split(LOADER).length - 1, route).toBe(1);
      const regional = html.indexOf("gtag('consent', 'default'");
      const global = html.indexOf("gtag('consent', 'default'", regional + 1);
      const update = html.indexOf("gtag('consent', 'update'", global);
      const config = html.indexOf(`gtag('config', "${MEASUREMENT_ID}"`);
      expect(regional, route).toBeGreaterThan(-1);
      expect(html.slice(regional, global), route).toContain(
        "analytics_storage: 'denied'",
      );
      expect(html.slice(global, config), route).toContain(
        "analytics_storage: 'granted'",
      );
      expect(global, route).toBeGreaterThan(regional);
      expect(html.indexOf('globalPrivacyControl'), route).toBeGreaterThan(
        global,
      );
      expect(update, route).toBeGreaterThan(global);
      expect(config, route).toBeGreaterThan(update);
      expect(html.indexOf(LOADER), route).toBeGreaterThan(config);
      // One cookie control per page.
      expect(
        html.match(/\sdata-cookie-control[\s>]/g) ?? [],
        route,
      ).toHaveLength(1);
    }
  });

  test('the config counts the path without the query', async ({ page }) => {
    await page.goto('/app/polygon/?cell=8a2a1072b59ffff#boundary');
    const config = (await gtagCalls(page)).find(
      ([command]) => command === 'config',
    );
    expect(config).toEqual([
      'config',
      MEASUREMENT_ID,
      {
        allow_ad_personalization_signals: false,
        allow_google_signals: false,
        page_location: new URL('/app/polygon/', page.url()).href,
        send_page_view: true,
      },
    ]);
  });
});

test.describe('opt-in in an EEA, UK or Swiss time zone', () => {
  test.use({ timezoneId: BERLIN });

  test('the control opens as the opt-in prompt without taking focus; analytics stays denied until Accept', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeVisible();
    await expect(cornerIcon(page)).toHaveAttribute('aria-expanded', 'true');
    const accept = panel(page).getByRole('button', { name: 'Accept' });
    const decline = panel(page).getByRole('button', { name: 'Decline' });
    await expect(accept).toBeVisible();
    await expect(decline).toBeVisible();
    await expect(analyticsSwitch(page)).toHaveCount(0);
    await expect(
      panel(page).getByRole('link', { name: 'Privacy' }),
    ).toHaveAttribute('href', '/privacy/');
    expect(
      await page.evaluate(() => document.activeElement === document.body),
    ).toBe(true);
    // Equal prominence: the two choices share one look and one size.
    const [acceptLook, declineLook] = await panel(page)
      .locator('[data-consent-choice]')
      .evaluateAll((buttons) =>
        buttons.map((button) => {
          const style = getComputedStyle(button);
          const box = button.getBoundingClientRect();
          return [
            style.backgroundColor,
            style.color,
            style.borderColor,
            style.fontWeight,
            Math.round(box.width),
            Math.round(box.height),
          ];
        }),
      );
    expect(acceptLook).toEqual(declineLook);
    // Denied before the config, and nothing grants it.
    expect(await consentUpdates(page)).toEqual(['denied']);
    expect(await updatesBeforeConfig(page)).toBe(true);
    expect(await seriousAxeViolations(page)).toEqual([]);

    await accept.click();
    await expect(panel(page)).toBeHidden();
    expect(await storedChoice(page)).toBe('granted');
    expect(await consentUpdates(page)).toEqual(['denied', 'granted']);

    await page.goto('/contribute/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['granted']);
    expect(await updatesBeforeConfig(page)).toBe(true);
  });

  test('Decline stores denied and removes GA cookies', async ({
    page,
    baseURL,
  }) => {
    await page.context().addCookies([
      { name: '_ga', value: 'GA1.1.1.1', url: baseURL },
      { name: '_ga_TEST123', value: 'GS1.1.1', url: baseURL },
      { name: 'unrelated', value: 'kept', url: baseURL },
    ]);
    await page.goto('/working-groups/');
    await waitForCookieControl(page);
    await panel(page).getByRole('button', { name: 'Decline' }).click();
    await expect(panel(page)).toBeHidden();
    expect(await storedChoice(page)).toBe('denied');
    expect(await consentUpdates(page)).toEqual(['denied', 'denied']);
    const names = (await page.context().cookies()).map(({ name }) => name);
    expect(names).toEqual(['unrelated']);

    await page.reload();
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['denied']);
    // The settings now show the choice as a switch.
    await cornerIcon(page).click();
    await expect(analyticsSwitch(page)).toHaveAttribute(
      'aria-checked',
      'false',
    );
    await expect(
      panel(page).getByRole('button', { name: 'Accept' }),
    ).toHaveCount(0);
  });

  test('closing the prompt without a choice keeps it collapsed for the rest of the visit', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(panel(page)).toBeHidden();
    await page.goto('/project/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await storedChoice(page)).toBeNull();
    expect(await consentUpdates(page)).toEqual(['denied']);
    // The icon still offers the choice.
    await cornerIcon(page).click();
    await expect(
      panel(page).getByRole('button', { name: 'Accept' }),
    ).toBeVisible();

    // A new visit asks again; a click outside also closes it.
    const visit = await page
      .context()
      .browser()!
      .newContext({
        baseURL: new URL(page.url()).origin,
        timezoneId: BERLIN,
      });
    const next = await visit.newPage();
    await installAtlasBrowserFixture(next);
    await next.goto('/project/');
    await waitForCookieControl(next);
    await expect(panel(next)).toBeVisible();
    await next.mouse.click(10, 300);
    await expect(panel(next)).toBeHidden();
    await visit.close();
  });

  test('docs pages prompt too, and keyboard users reach the prompt from the icon', async ({
    page,
  }) => {
    await page.goto('/docs/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeVisible();
    await cornerIcon(page).focus();
    await page.keyboard.press('Tab');
    const accept = panel(page).getByRole('button', { name: 'Accept' });
    await expect(accept).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(panel(page)).toBeHidden();
    expect(await storedChoice(page)).toBe('granted');
  });
});

test.describe('opt-out elsewhere', () => {
  test.use({ timezoneId: NEW_YORK });

  test('the control rests collapsed with analytics on, and the switch turns it off and stores denied', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForCookieControl(page);
    await expect(cornerIcon(page)).toBeVisible();
    await expect(cornerIcon(page)).toHaveAttribute('aria-expanded', 'false');
    await expect(panel(page)).toBeHidden();
    // The opt-out default stands: no update, the global default grants analytics.
    expect(await consentUpdates(page)).toEqual([]);
    expect(await storedChoice(page)).toBeNull();

    await cornerIcon(page).click();
    await expect(panel(page)).toBeVisible();
    await expect(cornerIcon(page)).toHaveAttribute('aria-expanded', 'true');
    await expect(analyticsSwitch(page)).toHaveAttribute('aria-checked', 'true');
    await expect(
      panel(page).getByRole('button', { name: 'Accept' }),
    ).toHaveCount(0);
    await analyticsSwitch(page).click();
    await expect(analyticsSwitch(page)).toHaveAttribute(
      'aria-checked',
      'false',
    );
    await expect(panel(page)).toBeVisible();
    expect(await storedChoice(page)).toBe('denied');
    expect(await consentUpdates(page)).toEqual(['denied']);

    await page.reload();
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['denied']);
    expect(await updatesBeforeConfig(page)).toBe(true);
    await cornerIcon(page).click();
    await expect(analyticsSwitch(page)).toHaveAttribute(
      'aria-checked',
      'false',
    );
    await analyticsSwitch(page).click();
    expect(await storedChoice(page)).toBe('granted');
    expect(await consentUpdates(page)).toEqual(['denied', 'granted']);
  });

  test('Global Privacy Control turns analytics off by default; an explicit choice overrides it', async ({
    page,
  }) => {
    await sendGlobalPrivacyControl(page);
    await page.goto('/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['denied']);
    expect(await updatesBeforeConfig(page)).toBe(true);
    expect(await storedChoice(page)).toBeNull();

    await cornerIcon(page).click();
    await expect(analyticsSwitch(page)).toHaveAttribute(
      'aria-checked',
      'false',
    );
    const gpcNote = panel(page).getByText(
      'Off because your browser sends Global Privacy Control.',
    );
    await expect(gpcNote).toBeVisible();
    await analyticsSwitch(page).click();
    await expect(analyticsSwitch(page)).toHaveAttribute('aria-checked', 'true');
    await expect(gpcNote).toBeHidden();
    expect(await storedChoice(page)).toBe('granted');

    await page.reload();
    await waitForCookieControl(page);
    expect(await consentUpdates(page)).toEqual(['granted']);
  });

  for (const route of [
    '/',
    '/docs/deployment/',
    '/privacy/',
    '/app/polygon/?cell=8a2a1072b59ffff',
  ])
    test(`the icon on ${route} is keyboard-operable, and Escape or a click outside collapses it`, async ({
      page,
    }) => {
      await page.goto(route);
      await waitForCookieControl(page);
      const icon = cornerIcon(page);
      await expect(icon).toBeVisible();
      await expect(icon).toHaveAccessibleName('Cookie settings');
      await icon.focus();
      await page.keyboard.press('Enter');
      await expect(panel(page)).toBeVisible();
      await expect(icon).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(analyticsSwitch(page)).toBeFocused();
      await page.keyboard.press('Space');
      await expect(analyticsSwitch(page)).toHaveAttribute(
        'aria-checked',
        'false',
      );
      expect(await storedChoice(page)).toBe('denied');
      await page.keyboard.press('Escape');
      await expect(panel(page)).toBeHidden();
      await expect(icon).toBeFocused();
      await expect(icon).toHaveAttribute('aria-expanded', 'false');

      await icon.click();
      await expect(panel(page)).toBeVisible();
      await page.mouse.click(10, 200);
      await expect(panel(page)).toBeHidden();
    });

  test('the footer link opens the same panel, on site and docs pages', async ({
    page,
  }) => {
    for (const route of ['/', '/docs/deployment/']) {
      await page.goto(route);
      await waitForCookieControl(page);
      const link = footerSettings(page);
      await link.click();
      await expect(panel(page), route).toBeVisible();
      await expect(panel(page), route).toBeFocused();
      await expect(page.locator('[data-cookie-panel]'), route).toHaveCount(1);
      await page.keyboard.press('Escape');
      await expect(panel(page), route).toBeHidden();
      await expect(link, route).toBeFocused();
      expect(await storedChoice(page), route).toBeNull();
    }
  });

  test('the corner icon is small, quiet and clear of the header', async ({
    page,
  }) => {
    for (const route of ['/', '/docs/']) {
      await page.goto(route);
      await waitForCookieControl(page);
      const clearance = await iconClearance(cornerIcon(page), [
        '[data-site-header]',
        '.site-header',
        'header',
      ]);
      expect(clearance.hit, route).toBe(true);
      expect(clearance.inViewport, route).toBe(true);
      expect(clearance.overlaps, route).toEqual([]);
      expect(clearance.size.width, route).toBeGreaterThanOrEqual(28);
      expect(clearance.size.width, route).toBeLessThanOrEqual(32);
      expect(clearance.size.height, route).toBe(clearance.size.width);
    }
  });
});

/** Everything the Atlas icon must never cover. */
const ATLAS_CHROME = [
  '.site-header',
  '.atlas-controls',
  '.atlas-kicker',
  '.atlas-top-slot',
  '.atlas-legend',
  '.atlas-scene .cesium-viewer-bottom',
  '.atlas-data-credit a',
  '.atlas-right-rail > *',
  '.atlas-status-stack > *',
] as const;

for (const viewport of [
  { height: 900, width: 1440 },
  { height: 800, width: 1100 },
] as const) {
  test.describe(
    `the Atlas icon at ${viewport.width}x${viewport.height}`,
    { tag: '@desktop-chromium' },
    () => {
      test.use({ timezoneId: NEW_YORK, viewport });

      test('docks in the explorer corner, clear of the controls, legend and credits, and opens the panel', async ({
        page,
      }) => {
        test.setTimeout(90_000);
        await page.goto('/app/');
        await waitForAtlasReady(page);
        await waitForCookieControl(page);
        await expect(cornerIcon(page)).toBeHidden();
        const icon = page.locator('[data-cookie-dock]:visible');
        await expect(icon).toHaveCount(1);
        await expect(icon).toHaveAccessibleName('Cookie settings');
        const clearance = await iconClearance(icon, ATLAS_CHROME);
        expect(clearance).toEqual({
          hit: true,
          inViewport: true,
          overlaps: [],
          size: { height: 28, width: 28 },
        });

        await icon.focus();
        await page.keyboard.press('Enter');
        await expect(panel(page)).toBeVisible();
        await expect(panel(page)).toBeFocused();
        await expect(icon).toHaveAttribute('aria-expanded', 'true');
        const [iconBox, panelBox] = await Promise.all([
          icon.boundingBox(),
          panel(page).boundingBox(),
        ]);
        expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(iconBox!.y);
        expect(Math.abs(panelBox!.x - iconBox!.x)).toBeLessThanOrEqual(1);
        await page.keyboard.press('Escape');
        await expect(panel(page)).toBeHidden();
        await expect(icon).toBeFocused();
        // The Atlas kept its own layers: Escape belonged to the panel.
        await expect(controlsSheet(page)).toBeVisible();
      });
    },
  );
}

for (const profile of PHONE_PROFILES)
  test.describe(
    `the Atlas icon on a ${profile.name} phone`,
    { tag: '@mobile-chromium' },
    () => {
      test.use({ ...profile.use, timezoneId: NEW_YORK });

      test('rides in the credit row above every sheet state, clear of the sheet, its handle, the legend and the credits', async ({
        page,
      }) => {
        test.setTimeout(120_000);
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.goto('/app/');
        await waitForAtlasReady(page);
        await waitForCookieControl(page);
        await expect(cornerIcon(page)).toBeHidden();
        const icon = page.locator('[data-cookie-dock]:visible');
        const sheet = controlsSheet(page);
        for (const state of ['peek', 'half', 'full'] as const) {
          await setSheetState(sheet, state);
          await expect(icon, state).toHaveCount(1);
          await expect
            .poll(() =>
              iconClearance(icon, [
                // The icon's 3 px overhang may meet the Cesium credit block's box, never
                // its logo or links.
                ...ATLAS_CHROME.filter(
                  (selector) =>
                    selector !== '.atlas-scene .cesium-viewer-bottom',
                ),
                '.atlas-scene .cesium-credit-logoContainer',
                '.atlas-scene .cesium-viewer-bottom a',
                'aside.atlas-controls .atlas-sheet__handle',
              ]),
            )
            .toEqual({
              hit: true,
              inViewport: true,
              overlaps: [],
              size: { height: 20, width: 20 },
            });
          // It sits in the data credit row, which docks above the sheet, and does not grow it:
          // the docked stack's height keeps the globe's centre clear.
          const row = await icon.evaluate((element) => {
            const credit = element.closest<HTMLElement>('.atlas-data-credit');
            if (!credit) return null;
            const withIcon = credit.getBoundingClientRect().height;
            (element as HTMLElement).style.display = 'none';
            const without = credit.getBoundingClientRect().height;
            (element as HTMLElement).style.display = '';
            return { grows: withIcon - without };
          });
          expect(row, state).toEqual({ grows: 0 });
        }

        await setSheetState(sheet, 'peek');
        await icon.focus();
        await page.keyboard.press('Enter');
        await expect(panel(page)).toBeVisible();
        await expect(panel(page)).toBeFocused();
        // The sheet settles at peek after its state flips; the open panel follows the icon down,
        // above the credit row, and never covers the handle.
        await expect
          .poll(() =>
            page.evaluate(() => {
              const handle = document.querySelector(
                'aside.atlas-controls .atlas-sheet__handle',
              )!;
              const rect = handle.getBoundingClientRect();
              const hit = document.elementFromPoint(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2,
              );
              const prompt = document
                .querySelector('[data-cookie-panel]')!
                .getBoundingClientRect();
              return {
                handleReachable: hit !== null && handle.contains(hit),
                panelAboveHandle: prompt.bottom <= rect.top,
              };
            }),
          )
          .toEqual({ handleReachable: true, panelAboveHandle: true });
        await page.keyboard.press('Escape');
        await expect(panel(page)).toBeHidden();
        await expect(icon).toBeFocused();
        await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      });
    },
  );

test.describe(
  'the opt-in prompt on the Atlas phone layout',
  { tag: '@mobile-chromium' },
  () => {
    test.use({ timezoneId: BERLIN });

    test('opens above the credit row, clear of the sheet handle, and a tap on the handle closes it', async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      await waitForCookieControl(page);
      await expect(panel(page)).toBeVisible();
      const sheet = controlsSheet(page);
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      const layout = await page.evaluate(() => {
        const box = (selector: string) =>
          document.querySelector(selector)!.getBoundingClientRect();
        const prompt = box('[data-cookie-panel]');
        const handle = box('aside.atlas-controls .atlas-sheet__handle');
        const icon = Array.from(document.querySelectorAll('[data-cookie-dock]'))
          .map((element) => element.getBoundingClientRect())
          .find((rect) => rect.width > 0)!;
        return {
          aboveIcon: prompt.bottom <= icon.top,
          clearOfHandle: prompt.bottom <= handle.top,
          inViewport: prompt.top >= 0 && prompt.right <= innerWidth,
        };
      });
      expect(layout).toEqual({
        aboveIcon: true,
        clearOfHandle: true,
        inViewport: true,
      });
      expect(await consentUpdates(page)).toEqual(['denied']);

      await sheet.locator('.atlas-sheet__handle').click();
      await expect(panel(page)).toBeHidden();
      await expect(sheet).not.toHaveAttribute('data-sheet-state', 'peek');
      expect(await storedChoice(page)).toBeNull();
    });
  },
);

test.describe('privacy page', () => {
  test.use({ timezoneId: NEW_YORK });

  test('is linked from the footers, explains GA4, its cookies and the regional choice, and is axe-clean', async ({
    page,
  }) => {
    await page.goto('/docs/');
    await page
      .getByRole('navigation', { name: 'Site policies' })
      .getByRole('link', { name: 'Privacy' })
      .click();
    await expect(page).toHaveURL(/\/privacy\/$/);
    await page.goto('/');
    await page
      .getByRole('navigation', { name: 'Site policies' })
      .getByRole('link', { name: 'Privacy' })
      .click();
    await expect(page).toHaveURL(/\/privacy\/$/);
    await expect(page.locator('h1')).toHaveCount(1);
    const main = page.locator('main');
    for (const text of [
      'Google Analytics 4',
      '_ga',
      'European Economic Area, UK and Switzerland: opt-in.',
      'Everywhere else: opt-out.',
      'Global Privacy Control',
      'does not log or store IP addresses',
      'Google signals are off',
      'not in a cookie',
      'small cookie icon',
    ])
      await expect(main, text).toContainText(text);
    await expect(
      main.getByRole('link', { name: 'privacy policy' }),
    ).toHaveAttribute('href', 'https://policies.google.com/privacy');
    expect(await seriousAxeViolations(page)).toEqual([]);
    await waitForCookieControl(page);
    await main.getByRole('button', { name: 'Cookie settings' }).click();
    await expect(panel(page)).toBeVisible();
  });
});
