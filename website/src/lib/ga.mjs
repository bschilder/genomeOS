// @ts-check
/**
 * Google Analytics 4 for genome-os.org (#422, decision of 2026-10-10), with Google Consent Mode
 * v2 defaults per region: opt-in in the EEA, the UK and Switzerland, opt-out elsewhere, Global
 * Privacy Control honoured (consent model refined by the owner the same day).
 *
 * A build loads analytics only when its environment sets PUBLIC_GA_MEASUREMENT_ID, and only the
 * production Pages build does, from the repository variable GA_MEASUREMENT_ID. Local dev, the
 * unit-test, e2e-fixture and /genomeOS/ fallback builds, pull requests and forks load nothing.
 * (The browser tests build with a placeholder ID and stub Google's script.)
 *
 * Every page head reads this one module, so they share one gate: astro.config.mjs adds its tags to
 * every Starlight docs page and defines the ID for client code, and Analytics.astro adds the same
 * tags to the site layout and to /app/polygon/. Plain JavaScript because astro.config.mjs imports
 * it.
 */

import {
  CONSENT_COUNTRIES,
  CONSENT_STORAGE_KEY,
  CONSENT_TIME_ZONES,
} from './consent-policy.mjs';

/** Where gtag.js comes from. */
export const GA_SCRIPT_ORIGIN = 'https://www.googletagmanager.com';

/** A GA4 web-stream Measurement ID, such as G-ABC123DEF4. */
const MEASUREMENT_ID = /^G-[A-Z0-9]{4,16}$/;

/**
 * How long gtag.js holds hits for a consent update in the regions that default to denied, before
 * it sends them as cookieless pings.
 */
export const CONSENT_WAIT_MS = 500;

/**
 * The Measurement ID this build reports to, or null when it loads no analytics. A value that is
 * not a Measurement ID fails the build rather than shipping a tag that reports nowhere.
 *
 * @param {Readonly<Record<string, string | undefined>>} [env]
 * @returns {string | null}
 */
export function gaMeasurementId(env = process.env) {
  const id = (env.PUBLIC_GA_MEASUREMENT_ID ?? '').trim();
  if (id === '') return null;
  if (!MEASUREMENT_ID.test(id))
    throw new Error(
      `PUBLIC_GA_MEASUREMENT_ID must be a GA4 Measurement ID such as G-ABC123DEF4, got "${id}".`,
    );
  return id;
}

/**
 * The gtag.js URL for a Measurement ID.
 *
 * @param {string} id
 * @returns {string}
 */
export function gaScriptUrl(id) {
  return `${GA_SCRIPT_ORIGIN}/gtag/js?id=${id}`;
}

/**
 * The inline script that runs before gtag.js loads. In order:
 *
 * 1. the dataLayer queue and `gtag`;
 * 2. the consent defaults: every signal denied in the consent regions (Google applies it from the
 *    visitor's IP), then analytics granted and ad signals denied everywhere else;
 * 3. one consent update when the browser knows better than the default, the same rule as
 *    `resolveConsent` in consent.ts: the visitor's stored choice; else denied when the browser sends
 *    Global Privacy Control; else denied in an EEA, UK or Swiss time zone (opt-in);
 * 4. the config, which counts the page's path and never its query string or fragment (the Atlas
 *    query holds a camera position and /app/polygon/ a selected cell), with Google signals and ad
 *    personalisation off.
 *
 * @param {string} id
 * @returns {string}
 */
export function gaBootstrapScript(id) {
  const json = JSON.stringify;
  return `(function () {
  var dataLayer = (window.dataLayer = window.dataLayer || []);
  var gtag = (window.gtag = function () {
    dataLayer.push(arguments);
  });
  gtag('consent', 'default', {
    ad_personalization: 'denied',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    analytics_storage: 'denied',
    region: ${json(CONSENT_COUNTRIES)},
    wait_for_update: ${CONSENT_WAIT_MS},
  });
  gtag('consent', 'default', {
    ad_personalization: 'denied',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    analytics_storage: 'granted',
  });
  var analytics = null;
  try {
    var choice = window.localStorage.getItem(${json(CONSENT_STORAGE_KEY)});
    if (choice === 'granted' || choice === 'denied') analytics = choice;
  } catch (error) {}
  if (analytics === null && window.navigator && window.navigator.globalPrivacyControl === true)
    analytics = 'denied';
  if (analytics === null) {
    try {
      var zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (${json(CONSENT_TIME_ZONES)}.indexOf(zone) !== -1) analytics = 'denied';
    } catch (error) {}
  }
  if (analytics !== null) gtag('consent', 'update', { analytics_storage: analytics });
  gtag('js', new Date());
  var config = {
    allow_ad_personalization_signals: false,
    allow_google_signals: false,
    page_location: location.origin + location.pathname,
    send_page_view: true,
  };
  var referrer = document.referrer.split(/[?#]/)[0];
  if (referrer) config.page_referrer = referrer;
  gtag('config', ${json(id)}, config);
})();`;
}

/**
 * @typedef {object} GaHeadTag
 * @property {'script'} tag
 * @property {Record<string, string | boolean>} [attrs]
 * @property {string} [content]
 */

/**
 * A page's head tags: the bootstrap, then gtag.js. Empty for a build without a Measurement ID.
 * Shaped as Starlight head entries; Analytics.astro renders the same entries.
 *
 * @param {Readonly<Record<string, string | undefined>>} [env]
 * @returns {GaHeadTag[]}
 */
export function gaHead(env = process.env) {
  const id = gaMeasurementId(env);
  if (id === null) return [];
  return [
    { tag: 'script', content: gaBootstrapScript(id) },
    { tag: 'script', attrs: { async: true, src: gaScriptUrl(id) } },
  ];
}
