import { describe, expect, it } from 'vitest';

import type { SurfaceCell } from '../src/atlas/contracts';
import { colorForCell, heightForCell } from '../src/atlas/visual-encoding';

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
    expect(colorForCell(cell({ post_mean: 0 }), 'post_mean', [0, 1])).toBe(
      '#10213e',
    );
    expect(colorForCell(cell({ post_mean: 1 }), 'post_mean', [0, 1])).toBe(
      '#72e7c1',
    );
    expect(colorForCell(cell({ post_sd: 0 }), 'post_sd', [0, 1])).toBe(
      '#24144b',
    );
    expect(colorForCell(cell({ post_sd: 1 }), 'post_sd', [0, 1])).toBe(
      '#f4c86a',
    );
  });
});
