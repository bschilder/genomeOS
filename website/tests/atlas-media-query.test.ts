import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import {
  MOBILE_QUERY,
  createMediaQueryStore,
  useMediaQuery,
} from '../src/components/atlas/useMediaQuery';

function fakeMatchMedia(initial: boolean) {
  const listeners = new Set<() => void>();
  const queries: string[] = [];
  let matches = initial;
  const matchMedia = (query: string) => {
    queries.push(query);
    return {
      get matches() {
        return matches;
      },
      addEventListener: (_type: string, listener: () => void) =>
        listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) =>
        listeners.delete(listener),
    } as unknown as MediaQueryList;
  };
  return {
    listeners,
    matchMedia,
    queries,
    set(next: boolean) {
      matches = next;
      for (const listener of listeners) listener();
    },
  };
}

describe('phone breakpoint hook (mobile sheets design §A.1.4)', () => {
  it('uses the single existing mobile switch point', () => {
    expect(MOBILE_QUERY).toBe('(max-width: 52rem)');
  });

  it('reads and follows the media query', () => {
    const media = fakeMatchMedia(true);
    const store = createMediaQueryStore(MOBILE_QUERY, () => media.matchMedia);
    expect(store.getSnapshot()).toBe(true);
    expect(media.queries).toContain(MOBILE_QUERY);
    const onChange = vi.fn();
    const unsubscribe = store.subscribe(onChange);
    media.set(false);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot()).toBe(false);
    unsubscribe();
    expect(media.listeners.size).toBe(0);
  });

  it('renders the desktop layout on the server', () => {
    const phone = fakeMatchMedia(true);
    const store = createMediaQueryStore(MOBILE_QUERY, () => phone.matchMedia);
    expect(store.getServerSnapshot()).toBe(false);
    function Probe() {
      return String(useMediaQuery(MOBILE_QUERY));
    }
    // A phone-sized window makes the client snapshot `true`, so `'false'` can
    // only come from the server snapshot the hook hands to React.
    vi.stubGlobal('window', { matchMedia: phone.matchMedia });
    try {
      expect(createMediaQueryStore(MOBILE_QUERY).getSnapshot()).toBe(true);
      expect(renderToString(createElement(Probe))).toBe('false');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('reports no match without a window', () => {
    const store = createMediaQueryStore(MOBILE_QUERY);
    expect(store.getSnapshot()).toBe(false);
    expect(() => store.subscribe(() => {})()).not.toThrow();
  });
});
