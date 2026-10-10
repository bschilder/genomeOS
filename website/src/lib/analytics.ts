/**
 * Usage events for Google Analytics 4 (#422). Each event carries public identifiers only (a
 * catalog dataset id, a view name, an inspector kind), never a coordinate, a query string or
 * anything about the visitor.
 *
 * Only a build with PUBLIC_GA_MEASUREMENT_ID loads gtag (`ga.mjs`). In every other build the
 * check below is a constant, so the bundler drops the sending code; on a page without gtag the
 * call does nothing. It never throws.
 */

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

/** A sender with its own dedupe memory; `trackEvent` is the page's. */
export function createEventTracker(
  now: () => number = () => performance.now(),
): (event: AtlasEvent) => void {
  let previous: { key: string; at: number } | undefined;
  return (event) => {
    if (!import.meta.env.PUBLIC_GA_MEASUREMENT_ID) return;
    try {
      const gtag = pageGtag();
      if (!gtag) return;
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
