import { describe, expect, it } from 'vitest';

import { supportSchema, type ArtifactRef } from '../src/atlas/contracts';
import {
  SUPPORT_CODES,
  decodeGrid,
  decodeRender,
  GosaError,
} from '../src/atlas/gosa/decode';
import type { DecodedGrid } from '../src/atlas/gosa/types';
import {
  editFloats,
  goldenBytes,
  goldenCatalog,
  goldenSurfaceJson,
  gosaCode,
  onlyGrid,
  refWith,
  rewriteColumn,
  rewriteHeader,
  toBuffer,
} from './support/gosa-builder';

const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const grid = decodeGrid(toBuffer(goldenBytes(entry.url)), {
  entry,
  gridSha256,
});
const formatOne = catalog.artifacts.find((ref) => ref.artifact_format === 1)!;
const formatTwo = catalog.artifacts.find((ref) => ref.artifact_format >= 2)!;

function goldenRender(ref: ArtifactRef): Uint8Array<ArrayBuffer> {
  return goldenBytes(ref.web.render.url);
}

function decodeAs(
  ref: ArtifactRef,
  bytes: Uint8Array = goldenRender(ref),
  change: (ref: ArtifactRef) => ArtifactRef = (value) => value,
) {
  return decodeRender(toBuffer(bytes), {
    grid,
    ref: change(refWith(ref, 'render', bytes)),
  });
}

/** Decode the golden format-1 render tier against a changed copy of the loaded grid. */
function decodeOnGrid(change: (grid: DecodedGrid) => DecodedGrid) {
  const bytes = goldenRender(formatOne);
  return decodeRender(toBuffer(bytes), {
    grid: change(grid),
    ref: refWith(formatOne, 'render', bytes),
  });
}

/** The error a decode raises, or undefined. */
function thrown(run: () => unknown): unknown {
  try {
    run();
  } catch (error) {
    return error;
  }
  return undefined;
}

function expectIdentityMismatch(error: unknown, field: string): void {
  expect(error).toBeInstanceOf(GosaError);
  expect(error).toMatchObject({ code: 'identity' });
  expect((error as Error).message).toMatch(
    new RegExp(`Atlas artifact identity mismatch for ${field}`),
  );
}

describe('decodeRender on the golden fixtures', () => {
  it('mirrors supportSchema in SUPPORT_CODES', () => {
    expect([...SUPPORT_CODES]).toEqual(supportSchema.options);
  });

  it.each(catalog.artifacts.map((ref) => [ref.id, ref] as const))(
    '%s matches float32 of its canonical JSON',
    (_id, ref) => {
      const render = decodeAs(ref);
      const surface = goldenSurfaceJson(ref);
      expect(render.artifact).toEqual(surface.artifact);
      surface.cells.forEach((cell, row) => {
        expect(SUPPORT_CODES[render.support[row]]).toBe(cell.support);
        expect(render.post_mean[row]).toBe(Math.fround(cell.post_mean));
        expect(render.post_sd[row]).toBe(Math.fround(cell.post_sd));
      });
      expect(render.support.byteOffset).toBe(0);
      expect(render.post_mean.buffer.byteLength).toBe(
        render.post_mean.length * 4,
      );
    },
  );

  it('exercises every support code across the fixtures', () => {
    const codes = new Set(
      catalog.artifacts.flatMap((ref) => Array.from(decodeAs(ref).support)),
    );
    expect([...codes].sort()).toEqual([0, 1, 2, 3]);
  });

  it('accepts values outside metric_domains (colour and height clamp, numbers do not)', () => {
    const outside = catalog.artifacts.some((ref) => {
      const [meanLow, meanHigh] = ref.metric_domains.post_mean;
      const [sdLow, sdHigh] = ref.metric_domains.post_sd;
      return goldenSurfaceJson(ref).cells.some(
        (cell) =>
          cell.post_mean < meanLow ||
          cell.post_mean > meanHigh ||
          cell.post_sd < sdLow ||
          cell.post_sd > sdHigh,
      );
    });
    expect(outside).toBe(true);
    for (const ref of catalog.artifacts)
      expect(() => decodeAs(ref)).not.toThrow();
  });
});

describe('decodeRender binding to the catalog', () => {
  it('compares the support histogram with support_counts', () => {
    const state = SUPPORT_CODES[decodeAs(formatOne).support[0]];
    expect(
      gosaCode(() =>
        decodeAs(formatOne, undefined, (ref) => ({
          ...ref,
          support_counts: {
            ...ref.support_counts,
            [state]: (ref.support_counts[state] ?? 0) + 1,
          },
        })),
      ),
    ).toBe('cross_tier');
  });

  it.each([
    [
      'variant_id',
      (ref: ArtifactRef) => ({ ...ref, variant_id: 'chr1-1-A-C' }),
    ],
    ['label', (ref: ArtifactRef) => ({ ...ref, label: 'Another label' })],
    [
      'metric_domains',
      (ref: ArtifactRef) => ({
        ...ref,
        metric_domains: { ...ref.metric_domains, post_sd: [0, 0.5] },
      }),
    ],
  ] as const)('raises identity for a different %s', (field, change) => {
    expectIdentityMismatch(
      thrown(() =>
        decodeAs(
          formatOne,
          undefined,
          change as (ref: ArtifactRef) => ArtifactRef,
        ),
      ),
      field,
    );
  });

  it.each([
    ['post_mean', 0],
    ['post_mean', 1],
    ['post_sd', 0],
    ['post_sd', 1],
  ] as const)(
    'raises identity when only metric_domains.%s[%i] differs',
    (metric, bound) => {
      expectIdentityMismatch(
        thrown(() =>
          decodeAs(formatOne, undefined, (ref) => {
            const domain: [number, number] = [...ref.metric_domains[metric]];
            domain[bound] += 0.001;
            return {
              ...ref,
              metric_domains: { ...ref.metric_domains, [metric]: domain },
            };
          }),
        ),
        'metric_domains',
      );
    },
  );

  it('compares target-grid identity on a format-2 artifact', () => {
    expectIdentityMismatch(
      thrown(() =>
        decodeAs(formatTwo, undefined, (ref) => ({
          ...ref,
          target_grid_version: 'another-grid-version',
        })),
      ),
      'target_grid_version',
    );
  });

  it('binds n_cells, the source surface and the grid', () => {
    expect(
      gosaCode(() =>
        decodeAs(formatOne, undefined, (ref) => ({
          ...ref,
          n_cells: ref.n_cells + 1,
        })),
      ),
    ).toBe('n_cells');
    expect(
      gosaCode(() =>
        decodeAs(formatOne, undefined, (ref) => ({
          ...ref,
          surface_sha256: 'f'.repeat(64),
        })),
      ),
    ).toBe('source_sha256');
    expect(
      gosaCode(() =>
        decodeAs(formatOne, undefined, (ref) => ({
          ...ref,
          web: { ...ref.web, grid_sha256: '0'.repeat(64) },
        })),
      ),
    ).toBe('grid_sha256');
  });

  it('binds n_cells and grid_sha256 to the loaded grid when the catalog agrees', () => {
    expect(gosaCode(() => decodeOnGrid((loaded) => loaded))).toBe('no error');
    expect(
      gosaCode(() =>
        decodeOnGrid((loaded) => ({ ...loaded, n: loaded.n + 1 })),
      ),
    ).toBe('n_cells');
    expect(
      gosaCode(() =>
        decodeOnGrid((loaded) => ({ ...loaded, gridSha256: '0'.repeat(64) })),
      ),
    ).toBe('grid_sha256');
  });

  it('refuses render bytes that differ from the catalog digest', () => {
    const flipped = goldenRender(formatOne).slice();
    flipped[flipped.length - 1] ^= 0xff;
    expect(
      gosaCode(() => decodeRender(toBuffer(flipped), { grid, ref: formatOne })),
    ).toBe('container_sha256');
  });
});

describe('decodeRender structural and value errors', () => {
  const bytes = goldenRender(formatOne);

  it('raises header_schema for a missing identity or source and identity for a null-padded one', () => {
    expect(
      gosaCode(() =>
        decodeAs(
          formatOne,
          rewriteHeader(bytes, (header) => (header.artifact = null)),
        ),
      ),
    ).toBe('header_schema');
    expect(
      gosaCode(() =>
        decodeAs(
          formatOne,
          rewriteHeader(bytes, (header) => {
            (header.artifact as Record<string, unknown>).target_grid_source =
              null;
          }),
        ),
      ),
    ).toBe('identity');
    expect(
      gosaCode(() =>
        decodeAs(
          formatOne,
          rewriteHeader(
            bytes,
            (header) => (header.source_surface_sha256 = null),
          ),
        ),
      ),
    ).toBe('header_schema');
  });

  it('raises tier when a grid is decoded as a render tier', () => {
    const gridBytes = goldenBytes(entry.url);
    expect(gosaCode(() => decodeAs(formatOne, gridBytes))).toBe('tier');
  });

  it('raises columns for reordered columns and a wrong dtype', () => {
    expect(
      gosaCode(() =>
        decodeAs(
          formatOne,
          rewriteHeader(bytes, (header) => {
            [header.columns[1], header.columns[2]] = [
              header.columns[2],
              header.columns[1],
            ];
          }),
        ),
      ),
    ).toBe('columns');
    expect(
      gosaCode(() =>
        decodeAs(
          formatOne,
          rewriteHeader(bytes, (header) => (header.columns[1].dtype = 'f64')),
        ),
      ),
    ).toBe('columns');
  });

  it('raises support_code for a code above 3', () => {
    const mutated = rewriteColumn(bytes, 'support', (payload) => {
      const copy = payload.slice();
      copy[0] = 4;
      return copy;
    });
    expect(gosaCode(() => decodeAs(formatOne, mutated))).toBe('support_code');
  });

  it.each([
    ['post_mean', Number.NaN, 'non_finite'],
    ['post_mean', 1.5, 'value_range'],
    ['post_mean', -0.25, 'value_range'],
    ['post_sd', Number.POSITIVE_INFINITY, 'non_finite'],
    ['post_sd', -0.25, 'value_range'],
  ] as const)('raises %s=%s as %s', (column, value, code) => {
    const mutated = rewriteColumn(
      bytes,
      column,
      editFloats(4, (values) => {
        values[0] = value;
      }),
    );
    expect(gosaCode(() => decodeAs(formatOne, mutated))).toBe(code);
  });

  it('checks values before the catalog binding (intrinsic errors win)', () => {
    const mutated = rewriteColumn(
      bytes,
      'post_mean',
      editFloats(4, (values) => {
        values[0] = 2;
      }),
    );
    expect(
      gosaCode(() =>
        decodeAs(formatOne, mutated, (ref) => ({
          ...ref,
          label: 'Another label',
        })),
      ),
    ).toBe('value_range');
  });
});
