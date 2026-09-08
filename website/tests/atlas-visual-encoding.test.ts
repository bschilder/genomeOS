import { describe, expect, it } from 'vitest';

import type { SurfaceCell } from '../src/atlas/contracts';
import {
  colorForCell,
  defaultPalette,
  heightForCell,
  paletteStops,
} from '../src/atlas/visual-encoding';

const baseCell: SurfaceCell = {
  dist_nearest_obs_km: 25,
  h3_index: '83754efffffffff',
  post_mean: 0.5,
  post_sd: 0.25,
  posterior_contraction: 0.8,
  q025: 0.4,
  q975: 0.6,
  support: 'observed',
};

function cell(overrides: Partial<SurfaceCell> = {}): SurfaceCell {
  return { ...baseCell, ...overrides };
}

describe('atlas visual encoding', () => {
  it.each(['unknown', 'prior_dominated'] as const)(
    'never gives %s a height',
    (support) => {
      expect(heightForCell(cell({ support }), [0, 1], 3)).toBe(0);
    },
  );

  it('uses stable artifact-wide height domains', () => {
    expect(heightForCell(cell({ post_mean: 0 }), [0, 1], 1)).toBe(0);
    expect(heightForCell(cell({ post_mean: 0.5 }), [0, 1], 1)).toBe(90_000);
    expect(heightForCell(cell({ post_mean: 1 }), [0, 1], 2)).toBe(360_000);
    expect(heightForCell(cell({ post_mean: 2 }), [0, 1], 1)).toBe(180_000);
  });

  it('uses distinct, deterministic palette endpoints', () => {
    expect(defaultPalette('post_mean')).toBe('rainbow');
    expect(defaultPalette('post_sd')).toBe('plasma');
    expect(colorForCell(cell({ post_mean: 0 }), 'post_mean', [0, 1])).toBe(
      '#6e40aa',
    );
    expect(colorForCell(cell({ post_mean: 1 }), 'post_mean', [0, 1])).toBe(
      '#ff5e63',
    );
    expect(colorForCell(cell({ post_sd: 0 }), 'post_sd', [0, 1])).toBe(
      '#0d0887',
    );
    expect(colorForCell(cell({ post_sd: 1 }), 'post_sd', [0, 1])).toBe(
      '#f0f921',
    );
  });

  it.each([
    ['genome', '#10213e', '#72e7c1'],
    ['signal', '#24144b', '#f4c86a'],
    ['viridis', '#440154', '#fde725'],
    ['cividis', '#00204c', '#fee838'],
    ['plasma', '#0d0887', '#f0f921'],
    ['rainbow', '#6e40aa', '#ff5e63'],
    ['golden', '#241133', '#fff3bd'],
  ] as const)('exposes fixed %s endpoints', (palette, low, high) => {
    expect(paletteStops(palette)[0]).toBe(low);
    expect(paletteStops(palette).at(-1)).toBe(high);
    expect(
      colorForCell(cell({ post_mean: 0 }), 'post_mean', [0, 1], palette),
    ).toBe(low);
    expect(
      colorForCell(cell({ post_mean: 1 }), 'post_mean', [0, 1], palette),
    ).toBe(high);
  });

  it('uses every rainbow stop rather than reducing it to three colors', () => {
    expect(paletteStops('rainbow')).toEqual([
      '#6e40aa',
      '#417de0',
      '#1ac7c2',
      '#7bd34d',
      '#f2cf44',
      '#ff5e63',
    ]);
    expect(
      colorForCell(cell({ post_mean: 0.4 }), 'post_mean', [0, 1], 'rainbow'),
    ).toBe('#1ac7c2');
  });
});
