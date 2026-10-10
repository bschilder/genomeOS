/**
 * SSR-safe media-query subscription for the Atlas phone layout (Atlas design
 * §11; mobile sheets design 2026-10-07 §A.1.4). The server snapshot is always
 * the desktop layout, so hydration never mismatches.
 */

import { useMemo, useSyncExternalStore } from 'react';

export const MOBILE_QUERY = '(max-width: 52rem)';
/** A short explorer: landscape phones and zoomed desktops (§A.1.5, §A.1.7). */
export const SHORT_QUERY = '(max-width: 52rem) and (max-height: 34rem)';

type MatchMedia = (query: string) => MediaQueryList;

export interface MediaQueryStore {
  subscribe(onChange: () => void): () => void;
  getSnapshot(): boolean;
  getServerSnapshot(): boolean;
}

function windowMatchMedia(): MatchMedia | undefined {
  return typeof window === 'undefined'
    ? undefined
    : window.matchMedia.bind(window);
}

/**
 * The snapshot moves only when this query's own `change` event fires. Read
 * live, `matches` changes at the resize, before the browser dispatches the
 * events, so any render in between would switch some components a commit
 * early: the dataset picker could then move to the top slot in the same commit
 * as the sheet enables and keep focus that belongs to the sheet's handle
 * (mobile sheets design §A.1.4, §A.1.6).
 */
export function createMediaQueryStore(
  query: string,
  getMatchMedia: () => MatchMedia | undefined = windowMatchMedia,
): MediaQueryStore {
  const list = () => getMatchMedia()?.(query);
  let current: boolean | null = null;
  return {
    subscribe(onChange) {
      const media = list();
      if (!media) return () => {};
      const update = () => {
        current = media.matches;
        onChange();
      };
      media.addEventListener('change', update);
      // A change between the first read and now had no listener to hear it.
      if (current !== null && current !== media.matches) update();
      return () => media.removeEventListener('change', update);
    },
    getSnapshot: () => (current ??= list()?.matches ?? false),
    getServerSnapshot: () => false,
  };
}

export function useMediaQuery(query: string): boolean {
  const store = useMemo(() => createMediaQueryStore(query), [query]);
  return useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getServerSnapshot,
  );
}
