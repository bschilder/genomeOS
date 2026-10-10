/**
 * The Google Analytics head tags and their consent bootstrap (#422): regional defaults, then the
 * stored choice, Global Privacy Control or an opt-in time zone, all before the config.
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

/** Run the bootstrap as a page would, and return its gtag calls as plain arrays. */
function runBootstrap({
  href = 'https://genome-os.org/',
  referrer = '',
  stored = null,
  storageThrows = false,
  gpc,
  timeZone = 'America/New_York',
  timeZoneThrows = false,
}: PageStub = {}): unknown[][] {
  const url = new URL(href);
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
    document: { referrer },
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
  return (window.dataLayer as IArguments[]).map((call) => Array.from(call));
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
  it('runs the bootstrap, then loads gtag.js asynchronously', () => {
    const tags = gaHead({ PUBLIC_GA_MEASUREMENT_ID: ID });
    expect(tags).toEqual([
      { tag: 'script', content: gaBootstrapScript(ID) },
      {
        tag: 'script',
        attrs: {
          async: true,
          src: 'https://www.googletagmanager.com/gtag/js?id=G-TEST123',
        },
      },
    ]);
    expect(gaScriptUrl(ID)).toBe(
      'https://www.googletagmanager.com/gtag/js?id=G-TEST123',
    );
  });
});

describe('bootstrap', () => {
  it('sets both consent defaults before the config', () => {
    const calls = runBootstrap();
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

  it('applies a stored choice before the config, whatever the zone or GPC', () => {
    for (const stored of ['granted', 'denied'])
      for (const page of [
        { timeZone: 'America/New_York' },
        { timeZone: 'Europe/Berlin' },
        { timeZone: 'America/Los_Angeles', gpc: true },
      ]) {
        const calls = runBootstrap({ ...page, stored });
        expect(consentUpdates(calls), `${stored} ${page.timeZone}`).toEqual([
          stored,
        ]);
        const update = calls.findIndex((call) => call[1] === 'update');
        expect(update).toBeGreaterThan(1);
        expect(update).toBeLessThan(configIndex(calls));
      }
  });

  it('treats Global Privacy Control as an opt-out when there is no stored choice', () => {
    const calls = runBootstrap({ timeZone: 'America/Los_Angeles', gpc: true });
    expect(consentUpdates(calls)).toEqual(['denied']);
    expect(calls.findIndex((call) => call[1] === 'update')).toBeLessThan(
      configIndex(calls),
    );
    // Only a real `true` is the signal.
    for (const gpc of [false, 'true', 1, null])
      expect(
        consentUpdates(runBootstrap({ timeZone: 'America/Los_Angeles', gpc })),
        String(gpc),
      ).toEqual([]);
  });

  it('keeps analytics denied in an EEA, UK or Swiss time zone until a choice (opt-in)', () => {
    for (const timeZone of [
      'Europe/Berlin',
      'Europe/London',
      'Europe/Zurich',
      'Atlantic/Canary',
    ])
      expect(consentUpdates(runBootstrap({ timeZone })), timeZone).toEqual([
        'denied',
      ]);
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
