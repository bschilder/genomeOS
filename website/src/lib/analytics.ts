/**
 * Usage events for Google Analytics 4 (#422). Each event carries public identifiers only (a
 * catalog dataset id, a view name, an inspector kind), never a coordinate, a query string or
 * anything about the visitor.
 *
 * Which dataset someone opens can hint at a health interest (a sickle-cell or G6PD map, say), so
 * `atlas_dataset_open` is sent only after an explicit opt-in, wherever the visitor is: a stored
 * `granted` choice from Accept or the analytics switch. The opt-out default outside the opt-in
 * regions does not count, and neither does a choice the browser could not store. View and
 * inspector events follow the page's consent as before.
 *
 * Only a build with PUBLIC_GA_MEASUREMENT_ID loads gtag (`ga.mjs`). In every other build the
 * check below is a constant, so the bundler drops the sending code; on a page without gtag the
 * call does nothing, and while analytics is denied the head's gtag drops it. It never throws.
 */

import { readConsentChoice } from './consent';
import { pageGtag } from './gtag';

/** The Atlas actions the site counts. */
export type AtlasEvent =
  | { name: 'atlas_dataset_open'; params: { dataset_id: string } }
  | {
      name: 'atlas_view_change';
      params: { view: 'globe' | 'map' | 'perspective' };
    }
  | {
      name: 'atlas_inspector_open';
      params: { inspector: 'surface' | 'observation' };
    };

/** Identical consecutive events this close together are one action, such as a double click. */
export const EVENT_DEDUPE_MS = 1_000;

/** Events sent only after the visitor explicitly opted in, in any region. */
export const EXPLICIT_OPT_IN_EVENTS: ReadonlySet<AtlasEvent['name']> = new Set([
  'atlas_dataset_open',
]);

type ConsentStorage = Pick<Storage, 'getItem'> | null | undefined;

/** The page's `localStorage`, or null where the browser blocks it. */
function pageLocalStorage(): ConsentStorage {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** A sender with its own dedupe memory; `trackEvent` is the page's. */
export function createEventTracker(
  now: () => number = () => performance.now(),
  consentStorage: () => ConsentStorage = pageLocalStorage,
): (event: AtlasEvent) => void {
  let previous: { key: string; at: number } | undefined;
  return (event) => {
    if (!import.meta.env.PUBLIC_GA_MEASUREMENT_ID) return;
    try {
      const gtag = pageGtag();
      if (!gtag) return;
      if (
        EXPLICIT_OPT_IN_EVENTS.has(event.name) &&
        readConsentChoice(consentStorage()) !== 'granted'
      )
        return;
      const key = JSON.stringify([event.name, event.params]);
      const at = now();
      if (previous?.key === key && at - previous.at < EVENT_DEDUPE_MS) return;
      previous = { key, at };
      gtag('event', event.name, { ...event.params });
    } catch {
      // Analytics never breaks the page.
    }
  };
}

/** Send one Atlas event to GA4. */
export const trackEvent = createEventTracker();
