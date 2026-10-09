import { describe, expect, it } from 'vitest';

import {
  colorAtPosition,
  colorAtStops,
  colorBytesAtStops,
  heightFor,
  linearStops,
  normalizedValue,
  paletteStops,
  quantizeMetric,
  type PaletteId,
} from '../src/atlas/visual-encoding';
import { quantizeMetric as reexportedQuantizeMetric } from './legacy/support-material';
import { legacyColorAtStops } from './legacy/legacy-color';

const PALETTES: readonly PaletteId[] = [
  'genome',
  'signal',
  'viridis',
  'cividis',
  'plasma',
  'rainbow',
  'golden',
];
const SWEEP_POINTS = 100_000;

function bytesOf(hex: string): [number, number, number] {
  return [1, 3, 5].map((offset) =>
    Number.parseInt(hex.slice(offset, offset + 2), 16),
  ) as [number, number, number];
}

function sweepPositions(stopCount: number): number[] {
  const positions: number[] = [];
  for (let index = 0; index <= SWEEP_POINTS; index += 1)
    positions.push(index / SWEEP_POINTS);
  for (let stop = 0; stop < stopCount; stop += 1) {
    const at = stop / (stopCount - 1);
    positions.push(at - 1e-9, at, at + 1e-9);
  }
  positions.push(-0.25, 1.25);
  return positions;
}

describe('shared numeric palette colour (fast-load §B.6.5)', () => {
  it.each(PALETTES)(
    'matches the legacy hex arithmetic byte for byte across %s',
    (palette) => {
      const stops = paletteStops(palette);
      const linear = linearStops(palette);
      for (const t of sweepPositions(stops.length)) {
        const expected = legacyColorAtStops(stops, t);
        expect(colorBytesAtStops(linear, t)).toEqual(bytesOf(expected));
        expect(colorAtPosition(palette, t)).toBe(expected);
        expect(colorAtStops(stops, t)).toBe(expected);
      }
    },
  );

  it('keeps the pinned plasma midpoint', () => {
    expect(colorBytesAtStops(linearStops('plasma'), 0.5)).toEqual([
      0xcc, 0x47, 0x78,
    ]);
  });

  it('rejects a scale with fewer than two stops', () => {
    expect(() => colorBytesAtStops([[0, 0, 0]], 0.5)).toThrow(
      'a color scale needs at least two stops',
    );
    expect(() => colorAtStops(['#000000'], 0.5)).toThrow(
      'a color scale needs at least two stops',
    );
  });
});

describe('render-tier heights and bins (fast-load §B.2)', () => {
  it.each(['unknown', 'prior_dominated'] as const)(
    'never raises %s cells',
    (support) => {
      expect(heightFor(support, 0.9, [0, 1], 5)).toBe(0);
    },
  );

  it('scales the clamped domain position by 180 km and the exaggeration', () => {
    expect(heightFor('observed', 0.5, [0, 1], 1)).toBe(90_000);
    expect(heightFor('interpolated', 2, [0, 1], 2)).toBe(360_000);
    expect(heightFor('observed', 0.5, [0, 1], -1)).toBe(0);
    expect(heightFor('observed', 0.4, [0.4, 0.4], 1)).toBe(0);
  });

  it('normalises with the same clamp as the legacy mesh', () => {
    expect(normalizedValue(0.25, [0, 0.5])).toBe(0.5);
    expect(normalizedValue(-1, [0, 1])).toBe(0);
    expect(normalizedValue(3, [0, 1])).toBe(1);
  });

  it('keeps quantizeMetric identical where support-material re-exports it', () => {
    expect(reexportedQuantizeMetric).toBe(quantizeMetric);
    expect(quantizeMetric(0.5, [0, 1])).toBe(16);
    expect(quantizeMetric(1, [0, 1])).toBe(31);
  });

  it('bins with the same empty-domain rule and clamp as normalizedValue', () => {
    expect(quantizeMetric(0.4, [0.4, 0.4])).toBe(0);
    expect(quantizeMetric(-1, [0, 1])).toBe(0);
    expect(quantizeMetric(3, [0, 1])).toBe(31);
  });
});
