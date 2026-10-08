/** Shared fixtures for the fast-load geometry tests (spec 2026-10-07 §B.8). */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { getResolution, h3IndexToSplitLong } from 'h3-js';

import {
  atlasCatalogSchema,
  surfaceArtifactSchema,
  type ArtifactIdentity,
  type AtlasCatalog,
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

/** The website directory, so no path below depends on the working directory. */
const WEBSITE_DIR = resolve(import.meta.dirname, '../..');

export const GOLDEN_DIR = join(WEBSITE_DIR, 'tests/fixtures/atlas/golden');
export const PARITY_DIR = join(WEBSITE_DIR, 'tests/fixtures/atlas/parity');

/** The operator's staging tree. Like any path given on a command line, it resolves against the
 * working directory. An empty value counts as unset, as in the Part C `ATLAS_DATA_DIR` suites. */
const DATA_DIR_OVERRIDE = process.env.ATLAS_DATA_DIR || null;

/** Where the published tree lives: a staging tree after Part C, the export in Part B. */
export const ATLAS_DATA_ROOT = DATA_DIR_OVERRIDE
  ? resolve(DATA_DIR_OVERRIDE)
  : join(WEBSITE_DIR, 'public/data/atlas');

/** The artifacts the full-grid suites build on; a tree with data must list both. */
const FULL_GRID_ID = 'hbs-rs334';
const CYT_FULL_GRID_ID = 'cyt-il-6-174-c';

export interface PublishedSurface {
  id: string;
  path: string;
}

/** Every surface `root/catalog.json` lists, through each artifact's `surface_url` (a flat file
 * name in Part B, a content-addressed `downloads/…` key in a Part C staging tree), in catalog
 * order.
 *
 * The result is empty (no data, so the full-grid suites skip) only when `mustHaveData` is false
 * and the tree has no catalog, or holds none of the surfaces its catalog lists (the catalog-only
 * checkout after Part C). Every other gap throws, so a broken tree never becomes a skipped suite:
 * - a catalog that does not parse against `atlasCatalogSchema`, or that repeats an id;
 * - with `mustHaveData` (`ATLAS_DATA_DIR` is set), a missing catalog or any missing surface;
 * - without it, a tree holding some listed surfaces but not all;
 * - a tree with data whose catalog does not list both full-grid artifacts. */
export function publishedSurfacesIn(
  root: string,
  mustHaveData: boolean,
): PublishedSurface[] {
  const catalog = join(root, 'catalog.json');
  if (!existsSync(catalog)) {
    if (mustHaveData)
      throw new Error(
        `${root} has no catalog.json, so ATLAS_DATA_DIR does not name a staging tree`,
      );
    return [];
  }
  let artifacts: AtlasCatalog['artifacts'];
  try {
    artifacts = atlasCatalogSchema.parse(
      JSON.parse(readFileSync(catalog, 'utf8')),
    ).artifacts;
  } catch (error) {
    throw new Error(`${catalog} is not a valid Atlas catalog`, {
      cause: error,
    });
  }
  const surfaces = artifacts.map(({ id, surface_url }) => ({
    id,
    path: join(root, surface_url),
  }));
  const ids = new Set(surfaces.map(({ id }) => id));
  if (ids.size !== surfaces.length)
    throw new Error(`${catalog} lists an artifact id more than once`);
  const missing = surfaces.filter(({ path }) => !existsSync(path));
  if (!mustHaveData && missing.length === surfaces.length) return [];
  if (missing.length > 0)
    throw new Error(
      `${catalog} lists ${missing.length} of ${surfaces.length} surfaces that the tree does not ` +
        `hold: ${missing.map(({ id, path }) => `${id} (${path})`).join(', ')}`,
    );
  const unlisted = [FULL_GRID_ID, CYT_FULL_GRID_ID].filter(
    (id) => !ids.has(id),
  );
  if (unlisted.length > 0)
    throw new Error(
      `${catalog} does not list ${unlisted.join(' or ')}, so the full-grid suites cannot run`,
    );
  return surfaces;
}

/** Read once, at import: every B3 test imports this helper. */
const PUBLISHED_SURFACES = publishedSurfacesIn(
  ATLAS_DATA_ROOT,
  DATA_DIR_OVERRIDE !== null,
);

/** Every published surface the catalog lists, in catalog order (empty without data). */
export function publishedSurfaces(): PublishedSurface[] {
  return PUBLISHED_SURFACES.map((surface) => ({ ...surface }));
}

function publishedSurfacePath(id: string): string | null {
  return PUBLISHED_SURFACES.find((surface) => surface.id === id)?.path ?? null;
}

/** The published 77,844-cell HbS surface and the cyt-il-6-174-c surface: both present whenever the
 * tree has data, and always under `ATLAS_DATA_DIR`. */
export const FULL_GRID_SURFACE = publishedSurfacePath(FULL_GRID_ID);
export const CYT_FULL_GRID_SURFACE = publishedSurfacePath(CYT_FULL_GRID_ID);
export const hasFullGrid =
  FULL_GRID_SURFACE !== null && CYT_FULL_GRID_SURFACE !== null;
