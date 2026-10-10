// @ts-check
/**
 * Where genome-os.org asks before it sets analytics cookies (#422; consent model refined by the
 * owner on 2026-10-10): opt-in in the EEA, the UK and Switzerland, opt-out everywhere else.
 *
 * Two lists describe the same places. Google applies `CONSENT_COUNTRIES` from the visitor's IP:
 * there every consent signal defaults to denied, so no analytics cookie is set before an Accept.
 * The browser also reads its own time zone, with no network lookup, against `CONSENT_TIME_ZONES`:
 * a visitor in one of those zones is treated as opt-in too, and the cookie control opens as a short
 * Accept/Decline prompt on the first visit. Over-inclusion only asks a non-European for consent;
 * under-inclusion (a European in another zone) is still covered by Google's IP region default.
 *
 * Plain JavaScript because astro.config.mjs reads it through `ga.mjs`. The cookie control bundle
 * reads it too, so it holds nothing that names Google.
 */

/** The `localStorage` key that remembers a visitor's choice: `'granted'` or `'denied'`. */
export const CONSENT_STORAGE_KEY = 'genomeos-analytics-consent';

/**
 * The `sessionStorage` key set when an opt-in visitor closes the first-visit prompt without
 * choosing, so it stays collapsed for the rest of that visit. Never a cookie.
 */
export const PROMPT_DISMISSED_KEY = 'genomeos-analytics-prompt-dismissed';

/**
 * ISO 3166-1 alpha-2 codes of the EEA (the 27 EU states with Iceland, Liechtenstein and Norway),
 * the UK and Switzerland.
 */
export const CONSENT_COUNTRIES = /* @__PURE__ */ Object.freeze([
  // European Union
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
  // Rest of the EEA
  'IS',
  'LI',
  'NO',
  // United Kingdom and Switzerland
  'GB',
  'CH',
]);

/**
 * The IANA time zones of `CONSENT_COUNTRIES`. Browsers report a zone under its ICU name, which is
 * sometimes an older spelling (`Atlantic/Faeroe`) or a link (`Europe/Belfast` is London), so a
 * zone's other names are listed beside it. Zones of non-EEA Europe are left out on purpose:
 * Russia, Belarus, Ukraine, Moldova, Turkey, the western Balkans outside the EU, Andorra, Monaco,
 * San Marino, the Vatican, Gibraltar and the Crown dependencies (their IP region default, where
 * Google has one, still applies).
 */
export const CONSENT_TIME_ZONES = /* @__PURE__ */ Object.freeze([
  'Europe/Vienna', // AT
  'Europe/Brussels', // BE
  'Europe/Sofia', // BG
  'Asia/Nicosia', // CY
  'Asia/Famagusta', // CY
  'Europe/Nicosia', // CY, a link to Asia/Nicosia
  'Europe/Prague', // CZ
  'Europe/Berlin', // DE
  'Europe/Busingen', // DE
  'Europe/Copenhagen', // DK
  'Atlantic/Faroe', // the Faroes: Danish, outside the EEA; a harmless prompt
  'Atlantic/Faeroe', // the ICU spelling of Atlantic/Faroe
  'Europe/Tallinn', // EE
  'Europe/Madrid', // ES
  'Africa/Ceuta', // ES
  'Atlantic/Canary', // ES
  'Europe/Helsinki', // FI
  'Europe/Mariehamn', // FI (Åland)
  'Europe/Paris', // FR
  'Europe/Athens', // GR
  'Europe/Zagreb', // HR
  'Europe/Budapest', // HU
  'Europe/Dublin', // IE
  'Europe/Rome', // IT
  'Europe/Vilnius', // LT
  'Europe/Luxembourg', // LU
  'Europe/Riga', // LV
  'Europe/Malta', // MT
  'Europe/Amsterdam', // NL
  'Europe/Warsaw', // PL
  'Europe/Lisbon', // PT
  'Atlantic/Madeira', // PT
  'Atlantic/Azores', // PT
  'Europe/Bucharest', // RO
  'Europe/Stockholm', // SE
  'Europe/Ljubljana', // SI
  'Europe/Bratislava', // SK
  'Atlantic/Reykjavik', // IS
  'Europe/Vaduz', // LI
  'Europe/Oslo', // NO
  'Arctic/Longyearbyen', // NO (Svalbard)
  'Atlantic/Jan_Mayen', // NO, a link to Arctic/Longyearbyen
  'Europe/London', // GB
  'Europe/Belfast', // GB, a link to Europe/London
  'Europe/Zurich', // CH
]);

// Pure annotations let a build without analytics drop these lists with the unused control code.
const consentTimeZones = /* @__PURE__ */ new Set(CONSENT_TIME_ZONES);

/**
 * Whether a browser time zone is one where analytics is opt-in.
 *
 * @param {string | null | undefined} timeZone
 * @returns {boolean}
 */
export function isConsentTimeZone(timeZone) {
  return typeof timeZone === 'string' && consentTimeZones.has(timeZone);
}
