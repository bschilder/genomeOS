import { describe, expect, it } from 'vitest';
import {
  comparisonQueries,
  comparisonSearch,
  sameNavigation,
} from '../src/atlas/comparison';

describe('comparison navigation contract', () => {
  const a = {
    view: 'globe' as const,
    camera: { lon: 20, lat: 10, height: 1000000, heading: 0, pitch: -90 },
  };
  it('round-trips both complete independent panel queries', () => {
    const left = 'entity=hbs-rs334&version=v3%2Fmap-2026-08&metric=post_mean';
    const right =
      'entity=g6pd-deficiency&version=v3%2Fmap-2026-08&metric=post_sd';
    expect(comparisonQueries(comparisonSearch(left, right))).toEqual({
      left,
      right,
    });
  });
  it('treats circular camera angles as the same orientation', () => {
    expect(
      sameNavigation(a, {
        ...a,
        camera: { ...a.camera, heading: 360, lon: 380 },
      }),
    ).toBe(true);
  });
  it('does not substitute missing selections or versions', () => {
    expect(comparisonQueries('')).toBeNull();
    expect(() => comparisonQueries('left=entity%3Dx')).toThrow();
    expect(() =>
      comparisonQueries(comparisonSearch('entity=x', 'entity=y')),
    ).toThrow();
  });
  it('ignores only insignificant serialization noise, not zoom or view changes', () => {
    expect(
      sameNavigation(a, {
        ...a,
        camera: { ...a.camera, height: a.camera.height + 0.1 },
      }),
    ).toBe(true);
    expect(
      sameNavigation(a, {
        ...a,
        camera: { ...a.camera, height: a.camera.height * 2 },
      }),
    ).toBe(false);
    expect(sameNavigation(a, { ...a, view: 'map' })).toBe(false);
    expect(sameNavigation(a, { ...a, camera: { ...a.camera, lon: NaN } })).toBe(
      false,
    );
  });
});
