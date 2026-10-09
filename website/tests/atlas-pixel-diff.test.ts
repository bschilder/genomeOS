/** Pixel-difference counting for the fast-load parity figures (fast-load design §B.1). */
import { describe, expect, it } from 'vitest';

import { countPixelDifferences } from '../scripts/pixel-diff.mjs';

describe('countPixelDifferences', () => {
  it('counts pixels by their largest channel difference', () => {
    const before = new Uint8Array([
      10, 10, 10, 255, 10, 10, 10, 255, 10, 10, 10, 255, 10, 10, 10, 255,
    ]);
    const after = new Uint8Array([
      10, 10, 10, 255, 12, 10, 10, 255, 10, 13, 10, 255, 10, 10, 40, 255,
    ]);
    expect(countPixelDifferences(before, after, 2)).toEqual({
      pixels: 4,
      fractionAny: 0.75,
      fractionOverTolerance: 0.5,
      fractionOver16: 0.25,
    });
  });

  it('refuses buffers of different sizes', () => {
    expect(() =>
      countPixelDifferences(new Uint8Array(4), new Uint8Array(8), 2),
    ).toThrow('RGBA buffers differ in size');
  });
});
