/**
 * The Google Analytics head tags and their consent bootstrap (#422): regional defaults, then the
 * stored choice, Global Privacy Control or an opt-in time zone, all before the config; gtag.js
 * itself loads only while analytics is not denied in the browser (basic consent mode).
 */
import { runInNewContext } from 'node:vm';

import { describe, expect, it } from 'vitest';

import {
  CONSENT_COUNTRIES,
  CONSENT_STORAGE_KEY,
} from '../src/lib/consent-policy.mjs';
import {
  gaBootstrapScript,
  gaHead,
  gaMeasurementId,
  gaScriptUrl,
} from '../src/lib/ga.mjs';

const ID = 'G-TEST123';

interface PageStub {
  href?: string;
  referrer?: string;
  stored?: string | null;
  storageThrows?: boolean;
  gpc?: unknown;
  timeZone?: string;
  timeZoneThrows?: boolean;
}

interface BootedPage {
  /** The page's gtag calls so far, as plain arrays. */
  calls: () => unknown[][];
  /** The page's `window.gtag`, as later page code calls it. */
  gtag: (...args: unknown[]) => void;
  /** The `src` of each script the bootstrap added to the head, in order. */
  scripts: string[];
}

/** Run the bootstrap as a page would. */
function bootPage({
  href = 'https://genome-os.org/',
  referrer = '',
  stored = null,
  storageThrows = false,
  gpc,
  timeZone = 'America/New_York',
  timeZoneThrows = false,
}: PageStub = {}): BootedPage {
  const url = new URL(href);
  const scripts: string[] = [];
  const head = {
    appendChild: (element: { async?: boolean; src?: string }) => {
      expect(element.async).toBe(true);
      scripts.push(element.src ?? '');
      return element;
    },
  };
  const window: Record<string, unknown> = {
    localStorage: {
      getItem: (key: string) => {
        if (storageThrows) throw new Error('SecurityError');
        return key === CONSENT_STORAGE_KEY ? stored : null;
      },
    },
    navigator: gpc === undefined ? {} : { globalPrivacyControl: gpc },
  };
  runInNewContext(gaBootstrapScript(ID), {
    document: { createElement: () => ({}), head, referrer },
    Intl: {
      DateTimeFormat: () => ({
        resolvedOptions: () => {
          if (timeZoneThrows) throw new RangeError('no time zone');
          return { timeZone };
        },
      }),
    },
    location: { origin: url.origin, pathname: url.pathname },
    window,
  });
  return {
    calls: () =>
      (window.dataLayer as IArguments[]).map((call) => Array.from(call)),
    gtag: window.gtag as (...args: unknown[]) => void,
    scripts,
  };
}

/** Run the bootstrap as a page would, and return its gtag calls as plain arrays. */
function runBootstrap(page: PageStub = {}): unknown[][] {
  return bootPage(page).calls();
}

/** The commands of a page's gtag calls, in order. */
function commands(calls: unknown[][]): unknown[] {
  return calls.map(([command]) => command);
}

/** The analytics_storage of each consent update, in order. */
function consentUpdates(calls: unknown[][]): unknown[] {
  return calls
    .filter(([command, action]) => command === 'consent' && action === 'update')
    .map(
      (call) => (call[2] as { analytics_storage: unknown }).analytics_storage,
    );
}

function configIndex(calls: unknown[][]): number {
  return calls.findIndex(([command]) => command === 'config');
}

describe('Measurement ID gate', () => {
  it('loads nothing without PUBLIC_GA_MEASUREMENT_ID', () => {
    expect(gaMeasurementId({})).toBeNull();
    expect(gaMeasurementId({ PUBLIC_GA_MEASUREMENT_ID: '' })).toBeNull();
    expect(gaMeasurementId({ PUBLIC_GA_MEASUREMENT_ID: '  ' })).toBeNull();
    expect(gaHead({})).toEqual([]);
  });

  it('accepts a GA4 Measurement ID', () => {
    expect(gaMeasurementId({ PUBLIC_GA_MEASUREMENT_ID: ID })).toBe(ID);
    expect(
      gaMeasurementId({ PUBLIC_GA_MEASUREMENT_ID: ' G-AB12CD34EF ' }),
    ).toBe('G-AB12CD34EF');
  });

  it('fails the build on anything else', () => {
    for (const raw of [
      'UA-12345-1',
      'g-test123',
      'G-',
      'G-TEST123"></script>',
      'GTM-ABC123',
    ])
      expect(
        () => gaMeasurementId({ PUBLIC_GA_MEASUREMENT_ID: raw }),
        raw,
      ).toThrow('PUBLIC_GA_MEASUREMENT_ID must be a GA4 Measurement ID');
  });
});

describe('head tags', () => {
  it('is the bootstrap alone, which adds gtag.js itself when it may load', () => {
    // No static loader: a <script src> in the head would fetch gtag.js before consent.
    const tags = gaHead({ PUBLIC_GA_MEASUREMENT_ID: ID });
    expect(tags).toEqual([{ tag: 'script', content: gaBootstrapScript(ID) }]);
    expect(gaScriptUrl(ID)).toBe(
      'https://www.googletagmanager.com/gtag/js?id=G-TEST123',
    );
    expect(gaBootstrapScript(ID)).toContain(JSON.stringify(gaScriptUrl(ID)));
  });
});

describe('bootstrap', () => {
  it('sets both consent defaults before the config, then loads gtag.js once', () => {
    const page = bootPage();
    const calls = page.calls();
    expect(page.scripts).toEqual([gaScriptUrl(ID)]);
    expect(calls.map((call) => call.slice(0, 2))).toEqual([
      ['consent', 'default'],
      ['consent', 'default'],
      ['js', calls[2]?.[1]],
      ['config', ID],
    ]);
    expect(calls[0]?.[2]).toEqual({
      ad_personalization: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      analytics_storage: 'denied',
      region: [...CONSENT_COUNTRIES],
      wait_for_update: 500,
    });
    expect(calls[1]?.[2]).toEqual({
      ad_personalization: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      analytics_storage: 'granted',
    });
  });

  it('configures a path-only page view with Google signals and ad personalisation off', () => {
    const calls = runBootstrap({
      href: 'https://genome-os.org/app/?entity=hbs-rs334&lat=40.4&lon=-3.7#cell',
      referrer: 'https://genome-os.org/app/polygon/?cell=8a2a1072b59ffff#x',
    });
    expect(calls.at(-1)).toEqual([
      'config',
      ID,
      {
        allow_ad_personalization_signals: false,
        allow_google_signals: false,
        page_location: 'https://genome-os.org/app/',
        page_referrer: 'https://genome-os.org/app/polygon/',
        send_page_view: true,
      },
    ]);
  });

  it('leaves the referrer out when there is none', () => {
    const config = runBootstrap({ href: 'https://genome-os.org/docs/' }).at(
      -1,
    )?.[2];
    expect(config).not.toHaveProperty('page_referrer');
  });

  it('sends no update outside the opt-in zones, so the opt-out default stands', () => {
    for (const timeZone of [
      'America/New_York',
      'Asia/Tokyo',
      'UTC',
      'Europe/Moscow',
    ])
      expect(consentUpdates(runBootstrap({ timeZone })), timeZone).toEqual([]);
  });

  it('applies a stored choice first, whatever the zone or GPC: granted loads, denied does not', () => {
    for (const page of [
      { timeZone: 'America/New_York' },
      { timeZone: 'Europe/Berlin' },
      { timeZone: 'America/Los_Angeles', gpc: true },
    ]) {
      const granted = bootPage({ ...page, stored: 'granted' });
      const calls = granted.calls();
      expect(consentUpdates(calls), page.timeZone).toEqual(['granted']);
      const update = calls.findIndex((call) => call[1] === 'update');
      expect(update).toBeGreaterThan(1);
      expect(update).toBeLessThan(configIndex(calls));
      expect(granted.scripts, page.timeZone).toEqual([gaScriptUrl(ID)]);

      const denied = bootPage({ ...page, stored: 'denied' });
      expect(consentUpdates(denied.calls()), page.timeZone).toEqual(['denied']);
      expect(commands(denied.calls()), page.timeZone).not.toContain('config');
      expect(denied.scripts, page.timeZone).toEqual([]);
    }
  });

  it('treats Global Privacy Control as an opt-out when there is no stored choice, and loads nothing', () => {
    const page = bootPage({ timeZone: 'America/Los_Angeles', gpc: true });
    expect(consentUpdates(page.calls())).toEqual(['denied']);
    expect(commands(page.calls())).not.toContain('config');
    expect(page.scripts).toEqual([]);
    // Only a real `true` is the signal.
    for (const gpc of [false, 'true', 1, null]) {
      const unsignalled = bootPage({ timeZone: 'America/Los_Angeles', gpc });
      expect(consentUpdates(unsignalled.calls()), String(gpc)).toEqual([]);
      expect(unsignalled.scripts, String(gpc)).toEqual([gaScriptUrl(ID)]);
    }
  });

  it('keeps analytics denied in an EEA, UK or Swiss time zone until a choice, without loading gtag.js (opt-in)', () => {
    for (const timeZone of [
      'Europe/Berlin',
      'Europe/London',
      'Europe/Zurich',
      'Atlantic/Canary',
      'Indian/Reunion',
    ]) {
      const page = bootPage({ timeZone });
      expect(consentUpdates(page.calls()), timeZone).toEqual(['denied']);
      // Basic consent mode: nothing reaches Google, not even a cookieless ping, before Accept.
      expect(commands(page.calls()), timeZone).not.toContain('config');
      expect(page.scripts, timeZone).toEqual([]);
    }
  });

  it('loads gtag.js when the visitor accepts, with the grant ahead of the config', () => {
    const page = bootPage({
      href: 'https://genome-os.org/app/?lat=48.1&lon=11.6',
      timeZone: 'Europe/Berlin',
    });
    page.gtag('consent', 'update', { analytics_storage: 'denied' });
    expect(page.scripts).toEqual([]);
    page.gtag('consent', 'update', { analytics_storage: 'granted' });
    expect(page.scripts).toEqual([gaScriptUrl(ID)]);
    const calls = page.calls();
    expect(consentUpdates(calls)).toEqual(['denied', 'denied', 'granted']);
    expect(commands(calls).slice(-3)).toEqual(['consent', 'js', 'config']);
    expect(calls.at(-1)?.[2]).toMatchObject({
      page_location: 'https://genome-os.org/app/',
    });
    // Once loaded, it stays loaded and configured once.
    page.gtag('consent', 'update', { analytics_storage: 'denied' });
    page.gtag('consent', 'update', { analytics_storage: 'granted' });
    expect(page.scripts).toHaveLength(1);
    expect(commands(page.calls()).filter((c) => c === 'config')).toHaveLength(
      1,
    );
    // An update that leaves analytics_storage out changes nothing.
    const other = bootPage({ timeZone: 'Europe/Berlin' });
    other.gtag('consent', 'update', { ad_storage: 'denied' });
    expect(other.scripts).toEqual([]);
  });

  it('drops events unless gtag.js is loading and analytics is not denied, so none waits for a later Accept', () => {
    const event = ['event', 'atlas_view_change', { view: 'map' }];
    const events = (page: BootedPage) =>
      page.calls().filter(([command]) => command === 'event');

    const optIn = bootPage({ timeZone: 'Europe/Berlin' });
    optIn.gtag(...event);
    expect(events(optIn)).toEqual([]);
    optIn.gtag('consent', 'update', { analytics_storage: 'granted' });
    optIn.gtag(...event);
    expect(events(optIn)).toEqual([event]);
    // Turned off on the page: later events stay in the page.
    optIn.gtag('consent', 'update', { analytics_storage: 'denied' });
    optIn.gtag(...event);
    expect(events(optIn)).toEqual([event]);

    const optOut = bootPage({ timeZone: 'America/New_York' });
    optOut.gtag(...event);
    expect(events(optOut)).toEqual([event]);
  });

  it('ignores an unknown stored value, blocked storage and a missing time zone', () => {
    for (const page of [
      { stored: 'maybe' },
      { storageThrows: true },
      { timeZoneThrows: true },
    ]) {
      const calls = runBootstrap(page);
      expect(consentUpdates(calls)).toEqual([]);
      expect(calls.at(-1)?.[0]).toBe('config');
    }
    expect(
      consentUpdates(runBootstrap({ storageThrows: true, gpc: true })),
    ).toEqual(['denied']);
  });
});
