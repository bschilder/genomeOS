/** Pixel-difference counting for the fast-load parity figures (fast-load design §B.1). */
import { describe, expect, it } from 'vitest';

import { countPixelDifferences, gateViews } from '../scripts/pixel-diff.mjs';

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

describe('gateViews', () => {
  const pair = (geometry: string, fractionOverTolerance: number) => ({
    entity: 'hbs-rs334',
    fractionOverTolerance,
    geometry,
  });

  it('passes a pair at the bound and fails one over it', () => {
    const { failed, views } = gateViews(
      { 'countries off': [pair('triangles', 0.005), pair('honmoon', 0.0051)] },
      0.005,
    );
    expect(views['countries off'].map(({ pass }) => pass)).toEqual([
      true,
      false,
    ]);
    expect(failed).toBe(true);
  });

  it('fails the run when only the every-layer view is over the bound', () => {
    const { failed, views } = gateViews(
      {
        'countries off': [pair('triangles', 0.0001)],
        'every layer': [pair('triangles', 0.012)],
      },
      0.005,
    );
    expect(views['every layer'][0]).toMatchObject({
      fractionOverTolerance: 0.012,
      geometry: 'triangles',
      pass: false,
    });
    expect(failed).toBe(true);
  });

  it('passes the run when every pair of every view is within the bound', () => {
    expect(
      gateViews(
        {
          'countries off': [pair('triangles', 0.0001)],
          'every layer': [pair('triangles', 0.0009)],
        },
        0.005,
      ).failed,
    ).toBe(false);
  });
});
