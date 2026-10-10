/**
 * Google Analytics 4, the cookie control and the Atlas events (#422; consent model refined by the
 * owner on 2026-10-10): opt-out by default, Global Privacy Control honoured, opt-in in EEA, UK and
 * Swiss time zones, and a small cookie icon on every page.
 *
 * `npm run test:e2e` builds with the placeholder Measurement ID G-TEST123, and the Atlas browser
 * fixture answers gtag.js with an empty stub, so every gtag call stays in the page's
 * window.dataLayer and none reaches Google. Where analytics is denied in the browser the page must
 * not even request gtag.js (basic consent mode), so the tests count those requests too.
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
/** gtag.js, as the head bootstrap names it (a JSON string), to add only where it may load. */
const LOADER_URL = JSON.stringify(
  `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`,
);
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

/** Count the page's gtag.js requests from now on. */
function gtagRequests(page: Page): () => number {
  let count = 0;
  page.on('request', (request) => {
    if (request.url().startsWith('https://www.googletagmanager.com/'))
      count += 1;
  });
  return () => count;
}

/** Whether the page queued a config (analytics started on this page). */
async function configured(page: Page): Promise<boolean> {
  return (await gtagCalls(page)).some(([command]) => command === 'config');
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

async function events(page: Page, name: string): Promise<unknown[]> {
  return (await gtagCalls(page))
    .filter(([command, event]) => command === 'event' && event === name)
    .map((call) => call[2]);
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
  test('every page has the bootstrap once, with the consent defaults and no static gtag.js loader', () => {
    const pages = htmlFiles(dist);
    const app = readFileSync(path.join(dist, 'app/index.html'), 'utf8');
    if (!app.includes(LOADER_URL))
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
      // The bootstrap adds gtag.js itself, and only where analytics may load: a static
      // <script src> would fetch it before consent. The browser tests below check the order the
      // bootstrap runs in.
      expect(html.split('googletagmanager.com').length - 1, route).toBe(1);
      expect(html.split(LOADER_URL).length - 1, route).toBe(1);
      expect(html, route).not.toMatch(
        /<script\b[^>]*\bsrc="https:\/\/www\.googletagmanager\.com/,
      );
      expect(html.indexOf(LOADER_URL), route).toBeLessThan(
        html.indexOf('</head>'),
      );
      const regional = html.indexOf("gtag('consent', 'default'");
      const global = html.indexOf("gtag('consent', 'default'", regional + 1);
      const update = html.indexOf("gtag('consent', 'update'", global);
      expect(regional, route).toBeGreaterThan(-1);
      expect(html.slice(regional, global), route).toContain(
        "analytics_storage: 'denied'",
      );
      expect(html.slice(global, update), route).toContain(
        "analytics_storage: 'granted'",
      );
      expect(global, route).toBeGreaterThan(regional);
      expect(html.indexOf('globalPrivacyControl', global), route).toBeLessThan(
        update,
      );
      expect(html, route).toContain(`gtag('config', "${MEASUREMENT_ID}"`);
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

  test('the control opens as the opt-in prompt without taking focus; analytics stays denied, and gtag.js unloaded, until Accept', async ({
    page,
  }) => {
    const requests = gtagRequests(page);
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
    // Denied, nothing grants it, and basic consent mode: no config and no gtag.js, so not even a
    // cookieless ping reaches Google before Accept.
    expect(await consentUpdates(page)).toEqual(['denied']);
    expect(await configured(page)).toBe(false);
    expect(requests()).toBe(0);
    expect(await seriousAxeViolations(page)).toEqual([]);

    await accept.click();
    await expect(panel(page)).toBeHidden();
    expect(await storedChoice(page)).toBe('granted');
    // Accept loads gtag.js on this page, with the grant ahead of the config.
    expect(await consentUpdates(page)).toEqual(['denied', 'granted']);
    expect(await updatesBeforeConfig(page)).toBe(true);
    await expect.poll(requests).toBe(1);

    await page.goto('/contribute/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['granted']);
    expect(await updatesBeforeConfig(page)).toBe(true);
    await expect.poll(requests).toBe(2);
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
    const requests = gtagRequests(page);
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
    expect(await configured(page)).toBe(false);
    expect(requests()).toBe(0);
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
    expect(await configured(page)).toBe(false);
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
    const requests = gtagRequests(page);
    await page.goto('/');
    await waitForCookieControl(page);
    await expect(cornerIcon(page)).toBeVisible();
    await expect(cornerIcon(page)).toHaveAttribute('aria-expanded', 'false');
    await expect(panel(page)).toBeHidden();
    // The opt-out default stands: no update, the global default grants analytics.
    expect(await consentUpdates(page)).toEqual([]);
    expect(await configured(page)).toBe(true);
    await expect.poll(requests).toBe(1);
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

    // Off: the next page does not load gtag.js at all.
    await page.reload();
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['denied']);
    expect(await configured(page)).toBe(false);
    expect(requests()).toBe(1);
    await cornerIcon(page).click();
    await expect(analyticsSwitch(page)).toHaveAttribute(
      'aria-checked',
      'false',
    );
    await analyticsSwitch(page).click();
    expect(await storedChoice(page)).toBe('granted');
    expect(await consentUpdates(page)).toEqual(['denied', 'granted']);
    expect(await updatesBeforeConfig(page)).toBe(true);
    await expect.poll(requests).toBe(2);
  });

  test('Global Privacy Control turns analytics off by default; an explicit choice overrides it', async ({
    page,
  }) => {
    await sendGlobalPrivacyControl(page);
    const requests = gtagRequests(page);
    await page.goto('/');
    await waitForCookieControl(page);
    await expect(panel(page)).toBeHidden();
    expect(await consentUpdates(page)).toEqual(['denied']);
    expect(await configured(page)).toBe(false);
    expect(requests()).toBe(0);
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
    await expect.poll(requests).toBe(1);

    await page.reload();
    await waitForCookieControl(page);
    expect(await consentUpdates(page)).toEqual(['granted']);
    expect(await updatesBeforeConfig(page)).toBe(true);
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

/**
 * Google Maps' own controls on /app/polygon/, measured on the live page (default UI, `v=weekly`,
 * 2026-10-10) at 1440x900, 1024x768, Pixel 7, 360x780 and 740x360, where each keeps these
 * offsets: the map type buttons and fullscreen at the top, the camera control and the Street View
 * Pegman stacked bottom-right, the Google logo bottom-left, and the Terms strip along the bottom
 * (drawn here from the logo to the right edge). The e2e build has no Maps key, so the test draws
 * their boxes where the map would put them.
 */
const GOOGLE_MAPS_CONTROLS: Record<string, Record<string, number>> = {
  'map type': { top: 10, left: 10, width: 192, height: 40 },
  fullscreen: { top: 10, right: 10, width: 40, height: 40 },
  'camera control': { bottom: 96, right: 10, width: 40, height: 40 },
  pegman: { bottom: 24, right: 10, width: 40, height: 40 },
  'Google logo': { bottom: 0, left: 5, width: 66, height: 26 },
  'Terms strip': { bottom: 0, left: 76, right: 0, height: 14 },
};

test.describe(
  'the cookie icon on the Google Map',
  { tag: '@desktop-chromium' },
  () => {
    test.use({ timezoneId: NEW_YORK });

    test("stays clear of Google Maps' own controls at every size", async ({
      page,
    }) => {
      for (const viewport of [
        { width: 1440, height: 900 },
        { width: 1024, height: 768 },
        { width: 412, height: 915 },
        { width: 360, height: 780 },
        { width: 740, height: 360 },
      ]) {
        const size = `${viewport.width}x${viewport.height}`;
        await page.setViewportSize(viewport);
        await page.goto('/app/polygon/?cell=85283473fffffff');
        await waitForCookieControl(page);
        await page.evaluate((controls) => {
          const map = document.querySelector('#polygon-map')!;
          for (const [name, box] of Object.entries(controls)) {
            const control = document.createElement('div');
            control.dataset.mapsControl = name;
            control.style.position = 'fixed';
            for (const [edge, px] of Object.entries(box))
              control.style.setProperty(edge, `${px}px`);
            map.append(control);
          }
        }, GOOGLE_MAPS_CONTROLS);
        const clearance = await iconClearance(
          cornerIcon(page),
          Object.keys(GOOGLE_MAPS_CONTROLS).map(
            (name) => `[data-maps-control="${name}"]`,
          ),
        );
        expect(clearance, size).toEqual({
          hit: true,
          inViewport: true,
          overlaps: [],
          size: { height: 30, width: 30 },
        });

        // The panel opens beside it, inside the viewport.
        await cornerIcon(page).click();
        await expect(panel(page), size).toBeVisible();
        const [icon, opened] = await Promise.all([
          cornerIcon(page).boundingBox(),
          panel(page).boundingBox(),
        ]);
        expect(opened!.y + opened!.height, size).toBeLessThanOrEqual(icon!.y);
        expect(opened!.x, size).toBeGreaterThanOrEqual(0);
        expect(opened!.x + opened!.width, size).toBeLessThanOrEqual(
          viewport.width,
        );
        await page.keyboard.press('Escape');
      }
    });
  },
);

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
      // Before a choice the Atlas's events stay in the page: none is queued for a later Accept.
      expect(await configured(page)).toBe(false);
      expect(await events(page, 'atlas_dataset_open')).toEqual([]);

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
      'Each lasts up to two years',
      'the site doesn’t load Google Analytics',
      'keeps this visit-level data for two months',
      'under the map controls on a wide screen',
    ])
      await expect(main, text).toContainText(text);
    // This build loads analytics, so the no-analytics note is absent.
    await expect(main.locator('[data-no-analytics]')).toHaveCount(0);
    await expect(
      main.getByRole('link', { name: 'privacy policy' }),
    ).toHaveAttribute('href', 'https://policies.google.com/privacy');
    expect(await seriousAxeViolations(page)).toEqual([]);
    await waitForCookieControl(page);
    await main.getByRole('button', { name: 'Cookie settings' }).click();
    await expect(panel(page)).toBeVisible();
  });
});

test.describe('Atlas events', { tag: '@desktop-chromium' }, () => {
  test.use({ timezoneId: NEW_YORK });

  test('dataset opens and view switches each fire once, with public parameters only', async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/app/');
    await waitForAtlasReady(page);
    const initial = await page
      .locator('[data-atlas-active]')
      .getAttribute('data-atlas-active');
    expect(initial).toBeTruthy();
    await expect
      .poll(() => events(page, 'atlas_dataset_open'))
      .toEqual([{ dataset_id: initial }]);
    expect(await events(page, 'atlas_view_change')).toEqual([]);

    const next =
      initial === 'g6pd-deficiency' ? 'hbs-rs334' : 'g6pd-deficiency';
    await page
      .getByRole('button', { name: /Select dataset\. Current dataset:/ })
      .click();
    await page.locator(`[role="option"][data-map-id="${next}"]`).click();
    await expect(page.locator(`[data-atlas-active="${next}"]`)).toBeVisible({
      timeout: 45_000,
    });
    await waitForAtlasReady(page);
    expect(await events(page, 'atlas_dataset_open')).toEqual([
      { dataset_id: initial },
      { dataset_id: next },
    ]);

    await page.locator('summary').filter({ hasText: /^Map$/ }).click();
    await page
      .locator('summary')
      .filter({ hasText: /^Inferred surface$/ })
      .click();
    for (const view of ['Map', 'Perspective', 'Globe']) {
      const control = page.getByRole('radio', { name: view });
      await control.check();
      await expect(control).toBeChecked();
    }
    expect(await events(page, 'atlas_view_change')).toEqual([
      { view: 'map' },
      { view: 'perspective' },
      { view: 'globe' },
    ]);
    expect(await events(page, 'atlas_dataset_open')).toHaveLength(2);
  });

  test('each inspector open fires once, by kind', async ({ page }) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const query = new URLSearchParams({
      heading: '0',
      height: '1000000',
      lat: '40.4407',
      lon: '-3.7201',
      pitch: '-90',
    });
    await page.goto(`/app/?${query}`);
    await waitForAtlasReady(page);
    await expect(page.locator('[data-atlas-values-ready="true"]')).toBeVisible({
      timeout: 45_000,
    });
    const canvas = page.locator('.atlas-scene canvas').first();
    const clickNearCenter = async (inspector: Locator) => {
      const box = await canvas.boundingBox();
      expect(box).not.toBeNull();
      for (const [x, y] of [
        [0, 0],
        [-18, 0],
        [18, 0],
        [0, -18],
        [0, 18],
        [-18, -18],
        [18, -18],
        [-18, 18],
        [18, 18],
      ]) {
        await page.mouse.click(
          box!.x + box!.width / 2 + x!,
          box!.y + box!.height / 2 + y!,
        );
        if (await inspector.isVisible()) return;
      }
    };

    await page
      .getByRole('checkbox', { name: 'Measured points', exact: true })
      .uncheck();
    await page
      .getByRole('checkbox', { name: 'Observation radii', exact: true })
      .uncheck();
    await expect
      .poll(() => new URL(page.url()).searchParams.get('layers'))
      .not.toContain('observations');
    const surface = page.getByRole('complementary', {
      name: 'Selected map cell',
    });
    await clickNearCenter(surface);
    await expect(surface).toBeVisible();
    expect(await events(page, 'atlas_inspector_open')).toEqual([
      { inspector: 'surface' },
    ]);
    await page.keyboard.press('Escape');
    await expect(surface).toHaveCount(0);

    await page
      .getByRole('checkbox', { name: 'Measured points', exact: true })
      .check();
    await page
      .getByRole('checkbox', { name: 'Observation radii', exact: true })
      .check();
    await page
      .getByRole('checkbox', { name: 'Inferred surface', exact: true })
      .uncheck();
    await expect(page).toHaveURL(/layers=[^&]*observations/);
    await page.waitForTimeout(650);
    const observation = page.getByRole('complementary', {
      name: 'Selected observation',
    });
    await clickNearCenter(observation);
    await expect(observation).toBeVisible();
    expect(await events(page, 'atlas_inspector_open')).toEqual([
      { inspector: 'surface' },
      { inspector: 'observation' },
    ]);
    // Nothing about the visitor or the place: only the three public events and their one parameter.
    for (const [command, , params] of await gtagCalls(page))
      if (command === 'event')
        expect(Object.keys(params as object)).toHaveLength(1);
  });
});
