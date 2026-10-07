import { cellToChildren } from 'h3-js';
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
    const columns = surface();
    let caught: unknown;
    try {
      cellAt(columns, 0);
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(DetailNotLoadedError);
    expect(caught).toMatchObject({
      artifactKey: artifactKeyFor(ref),
      name: 'DetailNotLoadedError',
    });
  });

  it('serves the published cell exactly once the detail tier is attached', () => {
    const columns = surface();
    columns.detail = decodeDetail(toBuffer(goldenBytes(ref.web.detail.url)), {
      grid,
      ref,
      render,
    });
    json.cells.forEach((cell, row) => {
      expect(cellAt(columns, row)).toEqual(cell);
    });
  });

  it.each([-1, 1.5, Number.NaN])('rejects row %s', (row) => {
    const columns = surface();
    expect(() => h3At(columns, row)).toThrow(RangeError);
    expect(() => renderAt(columns, row)).toThrow(RangeError);
  });

  it('rejects the row one past the end', () => {
    expect(() => renderAt(surface(), grid.n)).toThrow(RangeError);
  });
});
