/**
 * Analytics consent for genome-os.org (#422; consent model refined by the owner on 2026-10-10).
 *
 * - Outside the EEA, the UK and Switzerland analytics is opt-out: on unless the visitor turns it
 *   off, or their browser sends Global Privacy Control (which US state laws such as California's,
 *   Colorado's and Connecticut's require honouring as an opt-out).
 * - In those regions it is opt-in: Google's IP region default is denied, and a visitor in one of
 *   their time zones is asked once per visit with an Accept/Decline prompt. Wherever analytics is
 *   denied in the browser, the page does not load gtag.js at all (basic consent mode).
 * - An explicit choice made in the cookie control wins over both and is kept in `localStorage`,
 *   never in a cookie.
 *
 * The head bootstrap (`ga.mjs`) applies the same rule before gtag.js loads; this module is the
 * cookie control's copy of it, and the code that records and sends a new choice. Pure apart from
 * the storage, navigator and gtag it is handed.
 */

import {
  CONSENT_STORAGE_KEY,
  PROMPT_DISMISSED_KEY,
  isConsentTimeZone,
} from './consent-policy.mjs';
import { pageGtag } from './gtag';

export type ConsentChoice = 'granted' | 'denied';

/** Why analytics is on or off: what decided `ConsentState.analytics`. */
export type ConsentSource = 'choice' | 'gpc' | 'opt-in-region' | 'default';

export interface ConsentState {
  analytics: ConsentChoice;
  source: ConsentSource;
}

export interface ConsentInputs {
  /** The stored explicit choice, or null when the visitor has made none. */
  choice: ConsentChoice | null;
  /** Whether the browser sends Global Privacy Control. */
  gpc: boolean;
  /** The browser's IANA time zone, if it reports one. */
  timeZone: string | null | undefined;
}

/**
 * The visitor's analytics consent: an explicit choice wins; else Global Privacy Control opts out;
 * else an EEA, UK or Swiss time zone is opt-in (denied until Accept); else analytics is on.
 */
export function resolveConsent({
  choice,
  gpc,
  timeZone,
}: ConsentInputs): ConsentState {
  if (choice) return { analytics: choice, source: 'choice' };
  if (gpc) return { analytics: 'denied', source: 'gpc' };
  if (isConsentTimeZone(timeZone))
    return { analytics: 'denied', source: 'opt-in-region' };
  return { analytics: 'granted', source: 'default' };
}

/**
 * Whether the cookie control opens on load as the opt-in prompt: only for a visitor who has not
 * chosen, in an opt-in time zone, and has not closed the prompt earlier in this visit.
 */
export function shouldPromptOnLoad(
  state: ConsentState,
  dismissedThisVisit: boolean,
): boolean {
  return state.source === 'opt-in-region' && !dismissedThisVisit;
}

type ReadableStorage = Pick<Storage, 'getItem'>;
type WritableStorage = Pick<Storage, 'setItem'>;

/** The stored choice, or null when there is none (or storage is unavailable). */
export function readConsentChoice(
  storage: ReadableStorage | null | undefined,
): ConsentChoice | null {
  try {
    const value = storage?.getItem(CONSENT_STORAGE_KEY);
    return value === 'granted' || value === 'denied' ? value : null;
  } catch {
    return null;
  }
}

/** Remember a choice. False when storage refuses it (private mode, blocked storage). */
export function writeConsentChoice(
  storage: WritableStorage | null | undefined,
  choice: ConsentChoice,
): boolean {
  try {
    if (!storage) return false;
    storage.setItem(CONSENT_STORAGE_KEY, choice);
    return true;
  } catch {
    return false;
  }
}

/** Whether the opt-in prompt was closed without a choice earlier in this visit. */
export function readPromptDismissed(
  storage: ReadableStorage | null | undefined,
): boolean {
  try {
    return storage?.getItem(PROMPT_DISMISSED_KEY) === 'true';
  } catch {
    return false;
  }
}

/** Remember for this visit that the opt-in prompt was closed without a choice. */
export function writePromptDismissed(
  storage: WritableStorage | null | undefined,
): void {
  try {
    storage?.setItem(PROMPT_DISMISSED_KEY, 'true');
  } catch {
    // The prompt then opens again on the next page, which does no harm.
  }
}

/** Whether a browser sends Global Privacy Control (`navigator.globalPrivacyControl`). */
export function sendsGlobalPrivacyControl(navigator: unknown): boolean {
  try {
    // Not in the DOM typings yet: Firefox, Brave and DuckDuckGo send it, Chrome via extensions.
    const signal = (navigator as { globalPrivacyControl?: unknown } | null)
      ?.globalPrivacyControl;
    return signal === true;
  } catch {
    return false;
  }
}

/** The browser's IANA time zone, or undefined when it does not report one. */
export function browserTimeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

/**
 * Tell gtag the visitor's choice. On a page that has not loaded gtag.js because analytics was
 * denied, a grant loads it (the head bootstrap, `ga.mjs`). Ad signals stay denied whatever the
 * choice.
 */
export function applyConsentChoice(choice: ConsentChoice): void {
  try {
    pageGtag()?.('consent', 'update', { analytics_storage: choice });
  } catch {
    // Analytics never breaks the page.
  }
}

/**
 * The cookie domains GA may have written for a host: the host itself and each parent domain, so
 * `www.genome-os.org` yields `www.genome-os.org` and `genome-os.org`.
 */
export function cookieDomains(hostname: string): string[] {
  // An IP address has no parent domains, and cookies on it are host-only.
  if (hostname.includes(':') || /^[\d.]+$/.test(hostname)) return [];
  const labels = hostname.split('.').filter(Boolean);
  if (labels.length < 2) return [];
  const domains: string[] = [];
  for (let start = 0; start <= labels.length - 2; start += 1)
    domains.push(labels.slice(start).join('.'));
  return domains;
}

/** The GA cookie names in a `document.cookie` string: `_ga` and `_ga_<container>`. */
export function analyticsCookieNames(cookieHeader: string): string[] {
  return cookieHeader
    .split(';')
    .map((pair) => pair.split('=')[0]?.trim() ?? '')
    .filter((name) => name === '_ga' || name.startsWith('_ga_'));
}

/** Expire GA's cookies after an opt-out, so a visitor who had them keeps none. */
export function clearAnalyticsCookies(doc: Document): void {
  try {
    const expire = '=; Max-Age=0; path=/';
    for (const name of analyticsCookieNames(doc.cookie)) {
      doc.cookie = `${name}${expire}`;
      for (const domain of cookieDomains(doc.location.hostname))
        doc.cookie = `${name}${expire}; domain=.${domain}`;
    }
  } catch {
    // Analytics never breaks the page.
  }
}
