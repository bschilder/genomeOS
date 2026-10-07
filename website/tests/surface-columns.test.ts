import { cellToChildren, latLngToCell } from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  decodeDetail,
  decodeGrid,
  decodeRender,
} from '../src/atlas/gosa/decode';
import {
  artifactKeyFor,
  cellAt,
  DetailNotLoadedError,
  h3At,
  renderAt,
  rowForH3,
  type SurfaceArtifact,
} from '../src/atlas/surface-columns';
import {
  goldenBytes,
  goldenCatalog,
  goldenSurfaceJson,
  onlyGrid,
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
const detail = decodeDetail(toBuffer(goldenBytes(ref.web.detail.url)), {
  grid,
  ref,
  render,
});
const json = goldenSurfaceJson(ref);

function surface(): SurfaceArtifact {
  return {
    artifact: render.artifact,
    artifactKey: artifactKeyFor(ref),
    detail: null,
    grid,
    support: render.support,
    values: { post_mean: render.post_mean, post_sd: render.post_sd },
  };
}

function h3Value(cell: string): bigint {
  return BigInt(`0x${cell}`);
}

/**
 * At resolutions 3 and 4 every H3 low lane is 0xffffffff (digits 5–15 are all 7), so the golden
 * grid never lets `rowForH3`'s low-lane comparisons decide. The 343 res-7 descendants of one res-4
 * cell share two high lanes and vary in the low lane, half of them at or above 2^31.
 */
const RES7_CELLS = cellToChildren(latLngToCell(0, 0, 4), 7).sort((a, b) => {
  const left = h3Value(a);
  const right = h3Value(b);
  return left < right ? -1 : left > right ? 1 : 0;
});
/** Odd sorted positions form the grid; even positions are misses, including the first and last. */
const RES7_GRID = RES7_CELLS.filter((_, index) => index % 2 === 1);
const RES7_MISSES = RES7_CELLS.filter((_, index) => index % 2 === 0);

function res7Surface(): SurfaceArtifact {
  const values = RES7_GRID.map(h3Value);
  const n = values.length;
  return {
    artifact: render.artifact,
    artifactKey: 'synthetic:res-7',
    detail: null,
    grid: {
      gridSha256: 'synthetic-res-7',
      h3Hi: Uint32Array.from(values, (value) => Number(value >> 32n)),
      h3Lo: Uint32Array.from(values, (value) =>
        Number(BigInt.asUintN(32, value)),
      ),
      n,
      resolution: 7,
    },
    support: new Uint8Array(n),
    values: { post_mean: new Float32Array(n), post_sd: new Float32Array(n) },
  };
}

function thrownBy(run: () => unknown): unknown {
  try {
    run();
  } catch (error) {
    return error;
  }
  return undefined;
}

describe('columnar surface accessors', () => {
  it('keys an artifact by id, model version and data version', () => {
    expect(artifactKeyFor(ref)).toBe(
      `${ref.id}:${ref.model_version}:${ref.data_version}`,
    );
  });

  it('round-trips every cell between its row and its H3 index', () => {
    const columns = surface();
    json.cells.forEach((cell, row) => {
      expect(h3At(columns, row)).toBe(cell.h3_index);
      expect(rowForH3(columns, cell.h3_index)).toBe(row);
    });
  });

  it('round-trips every row of a res-7 grid whose low lanes decide the search', () => {
    const columns = res7Surface();
    const { h3Hi, h3Lo } = columns.grid;
    // The case exercises what it claims: high lanes tie, low lanes vary, some exceed 2^31 - 1.
    expect(new Set(h3Hi).size).toBe(2);
    expect(new Set(h3Lo).size).toBeGreaterThan(h3Hi.length / 2);
    expect(h3Lo.some((lo) => lo >= 2 ** 31)).toBe(true);
    RES7_GRID.forEach((cell, row) => {
      expect(h3At(columns, row)).toBe(cell);
      expect(rowForH3(columns, cell)).toBe(row);
    });
  });

  it('returns null for same-resolution misses before row 0, between rows and past the end', () => {
    const columns = res7Surface();
    const first = h3Value(RES7_GRID[0]);
    const last = h3Value(RES7_GRID[RES7_GRID.length - 1]);
    const before = RES7_MISSES.filter((cell) => h3Value(cell) < first);
    const after = RES7_MISSES.filter((cell) => h3Value(cell) > last);
    expect(before).toHaveLength(1);
    expect(after).toHaveLength(1);
    expect(RES7_MISSES.length - before.length - after.length).toBe(
      RES7_GRID.length - 1,
    );
    RES7_MISSES.forEach((cell) => {
      expect(rowForH3(columns, cell)).toBeNull();
    });
  });

  it('returns null for cells outside the grid and malformed indices', () => {
    const columns = surface();
    expect(
      rowForH3(
        columns,
        cellToChildren(json.cells[0].h3_index, ref.resolution + 1)[0],
      ),
    ).toBeNull();
    expect(rowForH3(columns, 'not-an-h3-index')).toBeNull();
    expect(rowForH3(columns, '')).toBeNull();
  });

  it('serves render values (float32) with the exact support label', () => {
    const columns = surface();
    json.cells.forEach((cell, row) => {
      expect(renderAt(columns, row)).toEqual({
        h3: cell.h3_index,
        post_mean: Math.fround(cell.post_mean),
        post_sd: Math.fround(cell.post_sd),
        support: cell.support,
      });
    });
  });

  it('refuses displayable numbers until the detail tier is loaded', () => {
    const caught = thrownBy(() => cellAt(surface(), 0));
    expect(caught).toBeInstanceOf(DetailNotLoadedError);
    expect(caught).toMatchObject({
      artifactKey: artifactKeyFor(ref),
      name: 'DetailNotLoadedError',
    });
  });

  it('serves the published cell exactly once the detail tier is attached', () => {
    const columns = surface();
    columns.detail = detail;
    json.cells.forEach((cell, row) => {
      expect(cellAt(columns, row)).toEqual(cell);
    });
  });

  it.each([-1, 1.5, Number.NaN, grid.n])(
    'rejects row %s from every accessor, with or without the detail tier',
    (row) => {
      const columns = surface();
      expect(() => h3At(columns, row)).toThrow(RangeError);
      expect(() => renderAt(columns, row)).toThrow(RangeError);
      expect(() => cellAt(columns, row)).toThrow(RangeError);
      columns.detail = detail;
      expect(() => cellAt(columns, row)).toThrow(RangeError);
    },
  );

  it('checks the row before the detail tier', () => {
    const caught = thrownBy(() => cellAt(surface(), grid.n));
    expect(caught).toBeInstanceOf(RangeError);
    expect(caught).not.toBeInstanceOf(DetailNotLoadedError);
  });
});
