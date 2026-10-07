/**
 * SSR-safe media-query subscription for the Atlas phone layout (Atlas design
 * §11; mobile sheets design 2026-10-07 §A.1.4). The server snapshot is always
 * the desktop layout, so hydration never mismatches.
 */

import { useMemo, useSyncExternalStore } from 'react';

export const MOBILE_QUERY = '(max-width: 52rem)';

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

export function createMediaQueryStore(
  query: string,
  getMatchMedia: () => MatchMedia | undefined = windowMatchMedia,
): MediaQueryStore {
  const list = () => getMatchMedia()?.(query);
  return {
    subscribe(onChange) {
      const media = list();
      if (!media) return () => {};
      media.addEventListener('change', onChange);
      return () => media.removeEventListener('change', onChange);
    },
    getSnapshot: () => list()?.matches ?? false,
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
