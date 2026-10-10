// @ts-check
/**
 * Where genome-os.org asks before it sets analytics cookies (#422; consent model refined by the
 * owner on 2026-10-10): opt-in in the EEA, the UK, Switzerland, Quebec and Turkey, opt-out
 * everywhere else. "Just to be safe", the opt-in places also include the parts of them that Google
 * geolocates as countries of their own (the EU's outermost regions and Åland) and the Crown
 * dependencies and Gibraltar, whose data protection laws follow the GDPR. Quebec (Law 25 keeps
 * tracking technology off by default) and Turkey (the KVKK cookie guideline asks explicit consent
 * for non-essential cookies) were added at review.
 *
 * Two lists describe these places. Google applies `CONSENT_COUNTRIES` from the visitor's IP:
 * there every consent signal defaults to denied, so no analytics cookie is set before an Accept.
 * The browser also reads its own time zone, with no network lookup, against `CONSENT_TIME_ZONES`:
 * a visitor in one of those zones is treated as opt-in too, and the cookie control opens as a short
 * Accept/Decline prompt on the first visit. Over-inclusion only asks a visitor elsewhere for
 * consent; under-inclusion (a visitor in one of these places set to another zone) is still covered
 * by Google's IP region default. Quebec shows both: browsers there report `America/Toronto`, which
 * Ontario shares, so Ontario is asked too; and the Magdalen Islands keep Atlantic time
 * (`America/Halifax`, shared with the Maritimes), so they rely on the IP default.
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
 * the UK and Switzerland; then the EU territory that has a code of its own, so Google's IP lookup
 * reports it apart from its state; then the Crown dependencies and Gibraltar; then Turkey, and
 * Quebec by its ISO 3166-2 subdivision code, which Consent Mode's `region` accepts.
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
  // EU territory with a country code of its own: France's outermost regions (Guadeloupe,
  // Martinique, French Guiana, Réunion, Mayotte, Saint-Martin) and Finland's Åland
  'GP',
  'MQ',
  'GF',
  'RE',
  'YT',
  'MF',
  'AX',
  // GDPR-equivalent law: Jersey, Guernsey, the Isle of Man and Gibraltar
  'JE',
  'GG',
  'IM',
  'GI',
  // Beyond Europe's GDPR area, "just to be safe": Turkey (KVKK) and Quebec (Law 25)
  'TR',
  'CA-QC',
]);

/**
 * The IANA time zones of `CONSENT_COUNTRIES`, the EU's outermost regions outside `Europe/*`
 * included. Browsers report a zone under its ICU name, which is sometimes an older spelling
 * (`Atlantic/Faeroe`) or a link (`Europe/Belfast` is London), so a zone's other names are listed
 * beside it. Zones of the rest of Europe are left out on purpose: Russia, Belarus, Ukraine,
 * Moldova, the western Balkans outside the EU, Andorra, Monaco, San Marino and the Vatican.
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
  'Europe/Mariehamn', // FI, Åland (AX)
  'Europe/Paris', // FR
  'America/Guadeloupe', // FR outermost region (GP)
  'America/Martinique', // FR outermost region (MQ)
  'America/Cayenne', // FR outermost region (GF)
  'Indian/Reunion', // FR outermost region (RE)
  'Indian/Mayotte', // FR outermost region (YT)
  'America/Marigot', // FR outermost region, Saint-Martin (MF)
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
  'Europe/Jersey', // JE
  'Europe/Guernsey', // GG
  'Europe/Isle_of_Man', // IM
  'Europe/Gibraltar', // GI
  'Europe/Istanbul', // TR
  'Asia/Istanbul', // TR, a link to Europe/Istanbul
  'America/Toronto', // CA-QC, most of Quebec; shared with Ontario, which is asked too
  'America/Montreal', // CA-QC, a link to America/Toronto that some systems still report
  'America/Blanc-Sablon', // CA-QC, the Lower North Shore
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
