import { describe, expect, it } from 'vitest';

import { surfaceCellView } from '../src/components/atlas/surface-cell-view';
import { columnarSurface } from './helpers/columnar-surface';

const CELL = '83754efffffffff';
const cells = [
  { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'interpolated' as const },
];

describe('surface cell view gate', () => {
  it('shows only the id and support until the detail tier loads', () => {
    const surface = columnarSurface(cells);
    const selection = {
      artifactKey: surface.artifactKey,
      kind: 'surface' as const,
      row: 0,
    };
    expect(surfaceCellView(surface, selection, 'loading')).toEqual({
      h3Index: CELL,
      state: 'loading',
      support: 'interpolated',
    });
    expect(surfaceCellView(surface, selection, 'ready')).toMatchObject({
      state: 'loading',
    });
    expect(surfaceCellView(surface, selection, 'unavailable')).toMatchObject({
      state: 'unavailable',
    });
  });

  it('takes every value from the detail tier once it is ready', () => {
    const surface = columnarSurface(cells, { withDetail: true });
    const view = surfaceCellView(
      surface,
      { artifactKey: surface.artifactKey, kind: 'surface', row: 0 },
      'ready',
    );
    expect(view).toMatchObject({ state: 'values' });
    if (view?.state !== 'values') throw new Error('expected values');
    expect(view.cell.post_mean).toBe(surface.detail!.post_mean[0]);
    expect(view.cell.q975).toBe(surface.detail!.q975[0]);
    expect(view.cell.h3_index).toBe(CELL);
  });

  it('drops a selection of another artifact or of a failed detail tier', () => {
    const surface = columnarSurface(cells, { withDetail: true });
    expect(
      surfaceCellView(
        surface,
        { artifactKey: 'other:v3:map-2026-08', kind: 'surface', row: 0 },
        'ready',
      ),
    ).toBeNull();
    expect(
      surfaceCellView(
        surface,
        { artifactKey: surface.artifactKey, kind: 'surface', row: 0 },
        'invalid',
      ),
    ).toBeNull();
    expect(
      surfaceCellView(
        null,
        { artifactKey: surface.artifactKey, kind: 'surface', row: 0 },
        'ready',
      ),
    ).toBeNull();
    expect(
      surfaceCellView(
        surface,
        { artifactKey: surface.artifactKey, kind: 'surface', row: 9 },
        'ready',
      ),
    ).toBeNull();
  });
});
