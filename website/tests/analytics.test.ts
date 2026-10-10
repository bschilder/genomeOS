/** Atlas usage events for GA4 (#422): a no-op without gtag, never throws, deduped. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  EVENT_DEDUPE_MS,
  createEventTracker,
  type AtlasEvent,
} from '../src/lib/analytics';

const dataset = (id: string): AtlasEvent => ({
  name: 'atlas_dataset_open',
  params: { dataset_id: id },
});
const view = (name: 'globe' | 'map' | 'perspective'): AtlasEvent => ({
  name: 'atlas_view_change',
  params: { view: name },
});

function clock() {
  let now = 10_000;
  return {
    now: () => now,
    advance: (ms: number) => {
      now += ms;
    },
  };
}

beforeEach(() => {
  vi.stubEnv('PUBLIC_GA_MEASUREMENT_ID', 'G-TEST123');
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('trackEvent', () => {
  it('sends each Atlas event to gtag with its public parameters', () => {
    const gtag = vi.fn();
    vi.stubGlobal('window', { gtag });
    const track = createEventTracker(clock().now);
    track(dataset('hbs-rs334'));
    track(view('map'));
    track({ name: 'atlas_inspector_open', params: { inspector: 'surface' } });
    expect(gtag.mock.calls).toEqual([
      ['event', 'atlas_dataset_open', { dataset_id: 'hbs-rs334' }],
      ['event', 'atlas_view_change', { view: 'map' }],
      ['event', 'atlas_inspector_open', { inspector: 'surface' }],
    ]);
  });

  it('drops an identical consecutive event within the dedupe window', () => {
    const gtag = vi.fn();
    vi.stubGlobal('window', { gtag });
    const time = clock();
    const track = createEventTracker(time.now);
    track(view('map'));
    time.advance(EVENT_DEDUPE_MS - 1);
    track(view('map'));
    expect(gtag).toHaveBeenCalledTimes(1);
    time.advance(EVENT_DEDUPE_MS);
    track(view('map'));
    expect(gtag).toHaveBeenCalledTimes(2);
    expect(EVENT_DEDUPE_MS).toBe(1_000);
  });

  it('keeps distinct events, and a repeat that is not consecutive', () => {
    const gtag = vi.fn();
    vi.stubGlobal('window', { gtag });
    const track = createEventTracker(clock().now);
    track(view('map'));
    track(view('globe'));
    track(view('map'));
    track(dataset('a'));
    track(dataset('b'));
    expect(gtag.mock.calls.map((call) => call[2])).toEqual([
      { view: 'map' },
      { view: 'globe' },
      { view: 'map' },
      { dataset_id: 'a' },
      { dataset_id: 'b' },
    ]);
  });

  it('is a no-op on a page without gtag', () => {
    vi.stubGlobal('window', {});
    const track = createEventTracker(clock().now);
    expect(() => track(view('map'))).not.toThrow();
  });

  it('is a no-op in a build without a Measurement ID, even beside a gtag', () => {
    vi.stubEnv('PUBLIC_GA_MEASUREMENT_ID', '');
    const gtag = vi.fn();
    vi.stubGlobal('window', { gtag });
    createEventTracker(clock().now)(view('map'));
    expect(gtag).not.toHaveBeenCalled();
  });

  it('never throws, even when gtag does', () => {
    vi.stubGlobal('window', {
      gtag: () => {
        throw new Error('blocked by an extension');
      },
    });
    const track = createEventTracker(clock().now);
    expect(() => track(dataset('hbs-rs334'))).not.toThrow();
  });

  it('copies the parameters, so gtag cannot alter the caller’s event', () => {
    const gtag = vi.fn((...args: unknown[]) => {
      (args[2] as Record<string, unknown>).page_location = 'mutated';
    });
    vi.stubGlobal('window', { gtag });
    const event = dataset('hbs-rs334');
    createEventTracker(clock().now)(event);
    expect(event.params).toEqual({ dataset_id: 'hbs-rs334' });
  });
});
