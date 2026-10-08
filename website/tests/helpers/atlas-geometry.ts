/** Shared fixtures for the fast-load geometry tests (spec 2026-10-07 §B.8). */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { getResolution, h3IndexToSplitLong } from 'h3-js';

import {
  surfaceArtifactSchema,
  type ArtifactIdentity,
  type SurfaceCell,
} from '../../src/atlas/contracts';
import { SUPPORT_CODES } from '../../src/atlas/gosa/decode';
import type { DecodedGrid } from '../../src/atlas/gosa/types';

/** A canonical surface JSON with its columns positional on `grid`. */
export interface SurfaceFixture {
  /** File name, so failures say which fixture broke. */
  name: string;
  artifact: ArtifactIdentity;
  cells: SurfaceCell[];
  /** The same cells with post_mean/post_sd rounded to f32 (the render tier). */
  froundCells: SurfaceCell[];
  grid: DecodedGrid;
  support: Uint8Array;
  // `Float32Array.from` returns `Float32Array<ArrayBuffer>`; declaring it so keeps these assignable
  // to `DecodedRender`'s columns under TS 5.7+ (a bare `Float32Array` is `ArrayBufferLike`).
  post_mean: Float32Array<ArrayBuffer>;
  post_sd: Float32Array<ArrayBuffer>;
}

function compareLanes(left: [number, number], right: [number, number]): number {
  return left[1] - right[1] || left[0] - right[0];
}

/** The unique cells in ascending u64 order, the order of every sorted grid. */
export function sortedU64(cells: Iterable<string>): string[] {
  return [...new Set(cells)].sort((left, right) =>
    BigInt(`0x${left}`) < BigInt(`0x${right}`) ? -1 : 1,
  );
}

/** A DecodedGrid over `h3` (which must be strictly increasing as u64). */
export function decodedGridFromH3(h3: readonly string[]): DecodedGrid {
  const h3Lo = new Uint32Array(h3.length);
  const h3Hi = new Uint32Array(h3.length);
  h3.forEach((index, row) => {
    const [low, high] = h3IndexToSplitLong(index);
    h3Lo[row] = low;
    h3Hi[row] = high;
    if (
      row > 0 &&
      compareLanes([h3Lo[row - 1], h3Hi[row - 1]], [low, high]) >= 0
    )
      throw new Error(`fixture grid not strictly increasing at row ${row}`);
  });
  return {
    gridSha256: 'test-grid',
    h3Hi,
    h3Lo,
    n: h3.length,
    resolution: h3.length > 0 ? getResolution(h3[0]) : 0,
  };
}

export function surfaceFixture(path: string): SurfaceFixture {
  const parsed = surfaceArtifactSchema.parse(
    JSON.parse(readFileSync(path, 'utf8')),
  );
  const cells = parsed.cells;
  const froundCells = cells.map((cell) => ({
    ...cell,
    post_mean: Math.fround(cell.post_mean),
    post_sd: Math.fround(cell.post_sd),
  }));
  return {
    artifact: parsed.artifact,
    cells,
    froundCells,
    grid: decodedGridFromH3(cells.map((cell) => cell.h3_index)),
    name: path.split('/').at(-1)!,
    post_mean: Float32Array.from(cells, (cell) => cell.post_mean),
    post_sd: Float32Array.from(cells, (cell) => cell.post_sd),
    support: Uint8Array.from(cells, (cell) =>
      SUPPORT_CODES.indexOf(cell.support),
    ),
  };
}

/** Every `*.surface.json` under the directory, in file-name order. */
export function surfaceFixturesIn(directory: string): SurfaceFixture[] {
  return readdirSync(directory)
    .filter((file) => file.endsWith('.surface.json'))
    .sort()
    .map((file) => surfaceFixture(join(directory, file)));
}

export const GOLDEN_DIR = 'tests/fixtures/atlas/golden';
export const PARITY_DIR = 'tests/fixtures/atlas/parity';

/** Where the published tree lives: a staging tree after Part C, the export in Part B. */
export const ATLAS_DATA_ROOT =
  process.env.ATLAS_DATA_DIR ?? 'public/data/atlas';

interface CatalogSurfaceRefs {
  artifacts: { id: string; surface_url: string }[];
}

/** The catalog's artifacts, or none when the tree has no catalog. Never throws: every B3 test
 * imports this helper, with or without data. */
function catalogSurfaceRefs(): CatalogSurfaceRefs['artifacts'] {
  const catalog = join(ATLAS_DATA_ROOT, 'catalog.json');
  if (!existsSync(catalog)) return [];
  try {
    return (JSON.parse(readFileSync(catalog, 'utf8')) as CatalogSurfaceRefs)
      .artifacts;
  } catch {
    return [];
  }
}

/** The canonical surface JSON of `id` through `catalog.json`'s `surface_url`, which is a flat file
 * name in Part B and a content-addressed `downloads/…` key in a Part C staging tree. */
function publishedSurfacePath(id: string): string | null {
  const ref = catalogSurfaceRefs().find((artifact) => artifact.id === id);
  if (!ref) return null;
  const path = join(ATLAS_DATA_ROOT, ref.surface_url);
  return existsSync(path) ? path : null;
}

/** Every published surface the catalog lists, in catalog order (empty without data). */
export function publishedSurfaces(): { id: string; path: string }[] {
  return catalogSurfaceRefs().flatMap(({ id }) => {
    const path = publishedSurfacePath(id);
    return path ? [{ id, path }] : [];
  });
}

/** The published 77,844-cell HbS surface and the cyt-il-6-174-c surface, when present. */
export const FULL_GRID_SURFACE = publishedSurfacePath('hbs-rs334');
export const CYT_FULL_GRID_SURFACE = publishedSurfacePath('cyt-il-6-174-c');
export const hasFullGrid =
  FULL_GRID_SURFACE !== null && CYT_FULL_GRID_SURFACE !== null;
