/**
 * Consent logic (#422, consent model refined 2026-10-10): opt-out by default, Global Privacy
 * Control honoured, opt-in in EEA, UK and Swiss time zones, and an explicit choice above all.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  analyticsCookieNames,
  applyConsentChoice,
  cookieDomains,
  readConsentChoice,
  readPromptDismissed,
  resolveConsent,
  sendsGlobalPrivacyControl,
  shouldPromptOnLoad,
  writeConsentChoice,
  writePromptDismissed,
  type ConsentChoice,
} from '../src/lib/consent';

function memoryStorage(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    items,
  };
}

const blockedStorage = {
  getItem: () => {
    throw new DOMException('blocked', 'SecurityError');
  },
  setItem: () => {
    throw new DOMException('full', 'QuotaExceededError');
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('stored consent choice', () => {
  it('reads only granted or denied', () => {
    expect(
      readConsentChoice(
        memoryStorage({ 'genomeos-analytics-consent': 'granted' }),
      ),
    ).toBe('granted');
    expect(
      readConsentChoice(
        memoryStorage({ 'genomeos-analytics-consent': 'denied' }),
      ),
    ).toBe('denied');
    expect(
      readConsentChoice(memoryStorage({ 'genomeos-analytics-consent': 'yes' })),
    ).toBeNull();
    expect(readConsentChoice(memoryStorage())).toBeNull();
  });

  it('treats missing or blocked storage as no choice', () => {
    expect(readConsentChoice(null)).toBeNull();
    expect(readConsentChoice(undefined)).toBeNull();
    expect(readConsentChoice(blockedStorage)).toBeNull();
  });

  it('writes the choice under its key and reports blocked storage', () => {
    const storage = memoryStorage();
    expect(writeConsentChoice(storage, 'denied')).toBe(true);
    expect(storage.items.get('genomeos-analytics-consent')).toBe('denied');
    expect(writeConsentChoice(storage, 'granted')).toBe(true);
    expect(readConsentChoice(storage)).toBe('granted');
    expect(writeConsentChoice(blockedStorage, 'granted')).toBe(false);
    expect(writeConsentChoice(null, 'granted')).toBe(false);
  });
});

describe('resolveConsent', () => {
  const NEW_YORK = 'America/New_York';
  const BERLIN = 'Europe/Berlin';

  it('is opt-out outside the EEA, UK and Switzerland: analytics on by default', () => {
    for (const timeZone of [NEW_YORK, 'Asia/Tokyo', 'UTC', undefined, null])
      expect(
        resolveConsent({ choice: null, gpc: false, timeZone }),
        String(timeZone),
      ).toEqual({ analytics: 'granted', source: 'default' });
  });

  it('is opt-in in an EEA, UK or Swiss time zone: denied until a choice', () => {
    for (const timeZone of [BERLIN, 'Europe/London', 'Europe/Zurich'])
      expect(
        resolveConsent({ choice: null, gpc: false, timeZone }),
        timeZone,
      ).toEqual({ analytics: 'denied', source: 'opt-in-region' });
  });

  it('treats Global Privacy Control as an opt-out when there is no stored choice', () => {
    for (const timeZone of [NEW_YORK, BERLIN])
      expect(
        resolveConsent({ choice: null, gpc: true, timeZone }),
        timeZone,
      ).toEqual({ analytics: 'denied', source: 'gpc' });
  });

  it('lets a stored choice win over the region and over GPC', () => {
    for (const choice of ['granted', 'denied'] as ConsentChoice[])
      for (const gpc of [false, true])
        for (const timeZone of [NEW_YORK, BERLIN])
          expect(
            resolveConsent({ choice, gpc, timeZone }),
            `${choice} ${gpc} ${timeZone}`,
          ).toEqual({ analytics: choice, source: 'choice' });
  });
});

describe('first-visit prompt', () => {
  it('opens only for an undecided visitor in an opt-in time zone', () => {
    const optIn = resolveConsent({
      choice: null,
      gpc: false,
      timeZone: 'Europe/Berlin',
    });
    expect(shouldPromptOnLoad(optIn, false)).toBe(true);
    for (const state of [
      resolveConsent({
        choice: null,
        gpc: false,
        timeZone: 'America/New_York',
      }),
      resolveConsent({ choice: null, gpc: true, timeZone: 'Europe/Berlin' }),
      resolveConsent({
        choice: 'denied',
        gpc: false,
        timeZone: 'Europe/Berlin',
      }),
      resolveConsent({
        choice: 'granted',
        gpc: false,
        timeZone: 'Europe/Berlin',
      }),
    ])
      expect(shouldPromptOnLoad(state, false), JSON.stringify(state)).toBe(
        false,
      );
  });

  it('stays collapsed for the rest of a visit once closed without a choice', () => {
    const session = memoryStorage();
    const optIn = resolveConsent({
      choice: null,
      gpc: false,
      timeZone: 'Europe/Paris',
    });
    expect(readPromptDismissed(session)).toBe(false);
    writePromptDismissed(session);
    expect(session.items.get('genomeos-analytics-prompt-dismissed')).toBe(
      'true',
    );
    expect(readPromptDismissed(session)).toBe(true);
    expect(shouldPromptOnLoad(optIn, readPromptDismissed(session))).toBe(false);
    expect(readPromptDismissed(blockedStorage)).toBe(false);
    expect(() => writePromptDismissed(blockedStorage)).not.toThrow();
  });
});

describe('Global Privacy Control', () => {
  it('reads only a real true from navigator.globalPrivacyControl', () => {
    expect(sendsGlobalPrivacyControl({ globalPrivacyControl: true })).toBe(
      true,
    );
    for (const value of [false, undefined, 'true', 1, null])
      expect(
        sendsGlobalPrivacyControl({ globalPrivacyControl: value }),
        String(value),
      ).toBe(false);
    expect(sendsGlobalPrivacyControl({})).toBe(false);
    expect(sendsGlobalPrivacyControl(undefined)).toBe(false);
  });
});

describe('consent update', () => {
  it('sends analytics_storage only, through the page gtag', () => {
    const gtag = vi.fn();
    vi.stubGlobal('window', { gtag });
    applyConsentChoice('granted');
    applyConsentChoice('denied');
    expect(gtag.mock.calls).toEqual([
      ['consent', 'update', { analytics_storage: 'granted' }],
      ['consent', 'update', { analytics_storage: 'denied' }],
    ]);
  });

  it('does nothing without gtag and never throws', () => {
    vi.stubGlobal('window', {});
    expect(() => applyConsentChoice('granted')).not.toThrow();
    vi.stubGlobal('window', {
      gtag: () => {
        throw new Error('blocked');
      },
    });
    expect(() => applyConsentChoice('denied')).not.toThrow();
  });
});

describe('analytics cookies on an opt-out', () => {
  it('finds _ga and _ga_<container> and nothing else', () => {
    expect(
      analyticsCookieNames(
        '_ga=GA1.1.1.1; theme=dark; _ga_TEST123=GS1.1; _gat=1; x_ga=1',
      ),
    ).toEqual(['_ga', '_ga_TEST123']);
    expect(analyticsCookieNames('')).toEqual([]);
  });

  it('expires them on the host and each parent domain', () => {
    expect(cookieDomains('www.genome-os.org')).toEqual([
      'www.genome-os.org',
      'genome-os.org',
    ]);
    expect(cookieDomains('genome-os.org')).toEqual(['genome-os.org']);
    expect(cookieDomains('localhost')).toEqual([]);
    expect(cookieDomains('127.0.0.1')).toEqual([]);
    expect(cookieDomains('[::1]')).toEqual([]);
  });
});
