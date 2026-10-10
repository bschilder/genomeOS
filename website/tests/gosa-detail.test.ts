import { describe, expect, it } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import {
  decodeDetail,
  decodeGrid,
  decodeRender,
} from '../src/atlas/gosa/decode';
import type { DecodedRender } from '../src/atlas/gosa/types';
import {
  editFloats,
  goldenBytes,
  goldenCatalog,
  goldenSurfaceJson,
  gosaCode,
  onlyGrid,
  refWith,
  rewriteColumn,
  toBuffer,
} from './support/gosa-builder';

const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const grid = decodeGrid(toBuffer(goldenBytes(entry.url)), {
  entry,
  gridSha256,
});
const ref = catalog.artifacts[0];
const render = decodeRender(toBuffer(goldenBytes(ref.web.render.url)), {
  grid,
  ref,
});
const golden = goldenBytes(ref.web.detail.url);
const cells = goldenSurfaceJson(ref).cells;

function decodeAs(
  bytes: Uint8Array = golden,
  options: {
    change?: (ref: ArtifactRef) => ArtifactRef;
    render?: DecodedRender;
  } = {},
) {
  const declared = refWith(ref, 'detail', bytes);
  return decodeDetail(toBuffer(bytes), {
    grid,
    ref: options.change ? options.change(declared) : declared,
    render: options.render ?? render,
  });
}

function editDetail(column: string, edit: (values: number[]) => void) {
  return rewriteColumn(golden, column, editFloats(8, edit));
}

describe('decodeDetail on the golden fixtures', () => {
  it.each(
    catalog.artifacts.map((artifact) => [artifact.id, artifact] as const),
  )('%s is bit-identical to its canonical JSON', (_id, artifact) => {
    const artifactRender = decodeRender(
      toBuffer(goldenBytes(artifact.web.render.url)),
      { grid, ref: artifact },
    );
    const detail = decodeDetail(
      toBuffer(goldenBytes(artifact.web.detail.url)),
      {
        grid,
        ref: artifact,
        render: artifactRender,
      },
    );
    goldenSurfaceJson(artifact).cells.forEach((cell, row) => {
      expect(Object.is(detail.post_mean[row], cell.post_mean)).toBe(true);
      expect(Object.is(detail.post_sd[row], cell.post_sd)).toBe(true);
      expect(Object.is(detail.q025[row], cell.q025)).toBe(true);
      expect(Object.is(detail.q975[row], cell.q975)).toBe(true);
      expect(
        Object.is(
          detail.posterior_contraction[row],
          cell.posterior_contraction,
        ),
      ).toBe(true);
      expect(
        Object.is(detail.dist_nearest_obs_km[row], cell.dist_nearest_obs_km),
      ).toBe(true);
    });
  });

  it('accepts the q025 == post_mean and post_mean == q975 boundaries the fixtures carry', () => {
    const all = catalog.artifacts.flatMap(
      (artifact) => goldenSurfaceJson(artifact).cells,
    );
    expect(all.some((cell) => cell.q025 === cell.post_mean)).toBe(true);
    expect(all.some((cell) => cell.post_mean === cell.q975)).toBe(true);
  });

  it('accepts a posterior contraction above one', () => {
    const mutated = editDetail('posterior_contraction', (values) => {
      values[0] = 1.7;
    });
    expect(decodeAs(mutated).posterior_contraction[0]).toBe(1.7);
  });
});

describe('decodeDetail hard errors', () => {
  it('raises interval_order when q025 > post_mean or post_mean > q975', () => {
    const row = cells.findIndex(
      (cell) => cell.post_mean < 0.995 && cell.post_mean > 0.005,
    );
    expect(row).toBeGreaterThanOrEqual(0);
    expect(
      gosaCode(() =>
        decodeAs(
          editDetail('q025', (values) => {
            values[row] = cells[row].post_mean + 0.005;
          }),
        ),
      ),
    ).toBe('interval_order');
    expect(
      gosaCode(() =>
        decodeAs(
          editDetail('q975', (values) => {
            values[row] = cells[row].post_mean - 0.005;
          }),
        ),
      ),
    ).toBe('interval_order');
  });

  it.each([
    ['q975', 1.25, 'value_range'],
    ['q025', -0.01, 'value_range'],
    ['dist_nearest_obs_km', -1, 'value_range'],
    ['posterior_contraction', Number.NaN, 'non_finite'],
    ['post_sd', Number.NEGATIVE_INFINITY, 'non_finite'],
  ] as const)('raises %s=%s as %s', (column, value, code) => {
    expect(
      gosaCode(() =>
        decodeAs(
          editDetail(column, (values) => {
            values[0] = value;
          }),
        ),
      ),
    ).toBe(code);
  });

  it('raises cross_tier when the render tier disagrees with float32 of the detail tier', () => {
    const shifted = {
      ...render,
      post_mean: Float32Array.from(render.post_mean, (value, row) =>
        row === 0
          ? Math.fround(value + 0.01 > 1 ? value - 0.01 : value + 0.01)
          : value,
      ),
    };
    expect(gosaCode(() => decodeAs(golden, { render: shifted }))).toBe(
      'cross_tier',
    );
    expect(
      gosaCode(() =>
        decodeAs(
          editDetail('post_sd', (values) => {
            values[0] += 1e-6;
          }),
        ),
      ),
    ).toBe('cross_tier');
  });

  it('binds the detail header to the catalog identity and digest', () => {
    expect(
      gosaCode(() =>
        decodeAs(golden, { change: (value) => ({ ...value, label: 'Other' }) }),
      ),
    ).toBe('identity');
    const flipped = golden.slice();
    flipped[flipped.length - 1] ^= 0xff;
    expect(
      gosaCode(() => decodeDetail(toBuffer(flipped), { grid, ref, render })),
    ).toBe('container_sha256');
  });
});
