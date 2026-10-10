import { cellToLatLng, gridDisk } from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  columnarHeightSource,
  surfaceHeightAt,
} from '../src/atlas/scene/surface-heights';
import { heightFor } from '../src/atlas/visual-encoding';
import { columnarSurface } from './helpers/columnar-surface';

const CELL = '83754efffffffff';
const NEIGHBOUR = gridDisk(CELL, 1).find((index) => index !== CELL)!;

describe('render-tier height sources', () => {
  it('reads heights from the f32 render columns at exaggeration 1', () => {
    const surface = columnarSurface([
      { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'observed' },
      { h3: NEIGHBOUR, post_mean: 0.9, post_sd: 0.1, support: 'unknown' },
    ]);
    const source = columnarHeightSource(surface);

    expect(source.artifactKey).toBe(surface.artifactKey);
    expect(source.resolution).toBe(3);
    expect(source.cellHeight(CELL, 'post_mean')).toBe(
      heightFor('observed', Math.fround(0.5), [0, 1], 1),
    );
    expect(source.cellHeight(NEIGHBOUR, 'post_mean')).toBe(0);
    expect(source.cellHeight('83754bfffffffff', 'post_mean')).toBeNull();
  });

  it('scales by exaggeration only when elevation is on', () => {
    const source = columnarHeightSource(
      columnarSurface([
        { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'observed' },
      ]),
    );
    const [lat, lon] = cellToLatLng(CELL);
    const flat = source.cellHeight(CELL, 'post_mean')!;

    expect(surfaceHeightAt({ lat, lon }, source, 'post_mean', true, 2)).toBe(
      flat * 2,
    );
    expect(surfaceHeightAt({ lat, lon }, source, 'post_mean', false, 2)).toBe(
      0,
    );
    expect(
      surfaceHeightAt({ lat: -60, lon: 120 }, source, 'post_mean', true, 2),
    ).toBe(0);
  });
});
