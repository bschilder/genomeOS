/** Where analytics is opt-in (#422, consent model refined by the owner on 2026-10-10). */
import { describe, expect, it } from 'vitest';

import {
  CONSENT_COUNTRIES,
  CONSENT_STORAGE_KEY,
  CONSENT_TIME_ZONES,
  PROMPT_DISMISSED_KEY,
  isConsentTimeZone,
} from '../src/lib/consent-policy.mjs';

const EU = [
  'AT',
  'BE',
  'BG',
  'CY',
  'CZ',
  'DE',
  'DK',
  'EE',
  'ES',
  'FI',
  'FR',
  'GR',
  'HR',
  'HU',
  'IE',
  'IT',
  'LT',
  'LU',
  'LV',
  'MT',
  'NL',
  'PL',
  'PT',
  'RO',
  'SE',
  'SI',
  'SK',
];

/**
 * Places where the GDPR (or a law modelled on it) applies that Google geolocates as countries of
 * their own, so the EEA's 30 codes alone miss them: the EU's outermost regions (Guadeloupe,
 * Martinique, French Guiana, Réunion, Mayotte, Saint-Martin), Åland, the Crown dependencies and
 * Gibraltar.
 */
const SEPARATELY_GEOLOCATED = ['GP', 'MQ', 'GF', 'RE', 'YT', 'MF', 'AX'];
const BRITISH_ISLES_GDPR_EQUIVALENT = ['JE', 'GG', 'IM', 'GI'];

/**
 * Their time zones, outside `Europe/*` for the outermost regions, so the Europe-wide
 * classification below cannot catch one missing.
 */
const GDPR_ZONES_OUTSIDE_EUROPE = [
  'America/Guadeloupe', // GP
  'America/Martinique', // MQ
  'America/Cayenne', // GF
  'Indian/Reunion', // RE
  'Indian/Mayotte', // YT
  'America/Marigot', // MF
];
const GDPR_EQUIVALENT_EUROPE = [
  'Europe/Mariehamn', // AX
  'Europe/Jersey', // JE
  'Europe/Guernsey', // GG
  'Europe/Isle_of_Man', // IM
  'Europe/Gibraltar', // GI
];

/**
 * Every `Europe/*` zone of a country outside the EEA, the UK, Switzerland, the Crown dependencies
 * and Gibraltar, under each name a browser may report. A zone the runtime knows must be listed
 * either here or in CONSENT_TIME_ZONES, so new tz data cannot slip through unclassified.
 */
const NON_CONSENT_EUROPE = [
  'Europe/Andorra',
  'Europe/Astrakhan', // RU
  'Europe/Belgrade', // RS
  'Europe/Chisinau', // MD
  'Europe/Istanbul', // TR
  'Europe/Kaliningrad', // RU
  'Europe/Kiev', // UA
  'Europe/Kirov', // RU
  'Europe/Kyiv', // UA
  'Europe/Minsk', // BY
  'Europe/Monaco',
  'Europe/Moscow', // RU
  'Europe/Podgorica', // ME
  'Europe/Samara', // RU
  'Europe/San_Marino',
  'Europe/Sarajevo', // BA
  'Europe/Saratov', // RU
  'Europe/Simferopol', // UA
  'Europe/Skopje', // MK
  'Europe/Tirane', // AL
  'Europe/Tiraspol', // MD
  'Europe/Ulyanovsk', // RU
  'Europe/Uzhgorod', // UA
  'Europe/Vatican',
  'Europe/Volgograd', // RU
  'Europe/Zaporozhye', // UA
];

/** The name a browser reports for a zone (ICU's canonical spelling). */
function reportedName(timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone }).resolvedOptions()
    .timeZone;
}

describe('consent regions', () => {
  it('denies by default in the EEA, the UK and Switzerland, each once', () => {
    expect([...CONSENT_COUNTRIES].sort()).toEqual(
      [
        ...EU,
        'IS',
        'LI',
        'NO',
        'GB',
        'CH',
        ...SEPARATELY_GEOLOCATED,
        ...BRITISH_ISLES_GDPR_EQUIVALENT,
      ].sort(),
    );
    expect(new Set(CONSENT_COUNTRIES).size).toBe(CONSENT_COUNTRIES.length);
    for (const code of CONSENT_COUNTRIES) expect(code).toMatch(/^[A-Z]{2}$/);
  });

  it('stores the choice and the prompt dismissal under documented keys', () => {
    expect(CONSENT_STORAGE_KEY).toBe('genomeos-analytics-consent');
    expect(PROMPT_DISMISSED_KEY).toBe('genomeos-analytics-prompt-dismissed');
  });
});

describe('consent time zones', () => {
  it('is opt-in in EEA, UK and Swiss zones, the Atlantic islands included', () => {
    for (const zone of [
      'Europe/Berlin',
      'Europe/Paris',
      'Europe/London',
      'Europe/Dublin',
      'Europe/Zurich',
      'Europe/Oslo',
      'Europe/Vaduz',
      'Europe/Helsinki',
      'Europe/Zagreb',
      'Asia/Nicosia',
      'Atlantic/Reykjavik',
      'Atlantic/Canary',
      'Atlantic/Madeira',
      'Atlantic/Azores',
      'Atlantic/Faroe',
    ])
      expect(isConsentTimeZone(zone), zone).toBe(true);
  });

  it('is opt-in in the EU outermost regions, Åland, the Crown dependencies and Gibraltar', () => {
    // A visitor in Réunion or Guadeloupe is in the EU: the browser asks before any cookie.
    for (const zone of [
      ...GDPR_ZONES_OUTSIDE_EUROPE,
      ...GDPR_EQUIVALENT_EUROPE,
    ])
      expect(isConsentTimeZone(zone), zone).toBe(true);
  });

  it('is opt-out outside them, non-EEA Europe included', () => {
    for (const zone of [
      ...NON_CONSENT_EUROPE,
      'America/New_York',
      'America/Sao_Paulo',
      'Asia/Tokyo',
      'Africa/Lagos',
      'Australia/Sydney',
      'UTC',
      'Etc/UTC',
      'GMT',
      '',
      'europe/berlin',
    ])
      expect(isConsentTimeZone(zone), zone).toBe(false);
    expect(isConsentTimeZone(undefined)).toBe(false);
    expect(isConsentTimeZone(null)).toBe(false);
  });

  it('lists only real zones, each once', () => {
    expect(new Set(CONSENT_TIME_ZONES).size).toBe(CONSENT_TIME_ZONES.length);
    for (const zone of [
      ...CONSENT_TIME_ZONES,
      ...NON_CONSENT_EUROPE,
      ...GDPR_ZONES_OUTSIDE_EUROPE,
      ...GDPR_EQUIVALENT_EUROPE,
    ])
      expect(() => reportedName(zone), zone).not.toThrow();
  });

  it('matches whichever name the browser reports for a listed zone', () => {
    // Chrome reports ICU names: Atlantic/Faroe as Atlantic/Faeroe, Europe/Belfast as Europe/London.
    for (const zone of CONSENT_TIME_ZONES)
      expect(isConsentTimeZone(reportedName(zone)), zone).toBe(true);
    for (const zone of NON_CONSENT_EUROPE)
      expect(isConsentTimeZone(reportedName(zone)), zone).toBe(false);
  });

  it('classifies every Europe/* zone this runtime knows', () => {
    const classified = new Set([...CONSENT_TIME_ZONES, ...NON_CONSENT_EUROPE]);
    const unclassified = Intl.supportedValuesOf('timeZone').filter(
      (zone) => zone.startsWith('Europe/') && !classified.has(zone),
    );
    expect(unclassified).toEqual([]);
  });
});
