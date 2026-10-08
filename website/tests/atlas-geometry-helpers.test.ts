/** The B3 helper's published-tree contract (fast-load spec 2026-10-07 §B.8; plan ruling R23): a
 * broken or partial tree fails loudly instead of skipping the full-grid suites. */

import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AtlasCatalog } from '../src/atlas/contracts';
import {
  GOLDEN_DIR,
  PARITY_DIR,
  publishedSurfacesIn,
} from './helpers/atlas-geometry';

const WEBSITE = path.resolve(import.meta.dirname, '..');
/** The repository catalog: it lists both full-grid artifacts, in either part of the plan. */
const CATALOG = JSON.parse(
  readFileSync(path.join(WEBSITE, 'public/data/atlas/catalog.json'), 'utf8'),
) as AtlasCatalog;
const HBS_URL = CATALOG.artifacts.find(
  ({ id }) => id === 'hbs-rs334',
)!.surface_url;

const trees: string[] = [];

/** A scratch tree holding `catalog` and an empty placeholder at every listed `surface_url` (the
 * helper only resolves paths), less `omit`. */
function tree(
  catalog: unknown = CATALOG,
  omit: readonly string[] = [],
): string {
  const root = mkdtempSync(path.join(tmpdir(), 'genomeos-atlas-tree-'));
  trees.push(root);
  writeFileSync(
    path.join(root, 'catalog.json'),
    typeof catalog === 'string' ? catalog : JSON.stringify(catalog),
  );
  for (const { surface_url } of CATALOG.artifacts) {
    if (omit.includes(surface_url)) continue;
    const file = path.join(root, surface_url);
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, '');
  }
  return root;
}

function emptyTree(): string {
  const root = mkdtempSync(path.join(tmpdir(), 'genomeos-atlas-empty-'));
  trees.push(root);
  return root;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  for (const root of trees.splice(0))
    rmSync(root, { force: true, recursive: true });
});

describe('published-tree resolution (fast-load §B.8, R23)', () => {
  it('resolves every listed surface through surface_url, in catalog order', () => {
    const root = tree();
    for (const mustHaveData of [false, true])
      expect(publishedSurfacesIn(root, mustHaveData)).toEqual(
        CATALOG.artifacts.map(({ id, surface_url }) => ({
          id,
          path: path.join(root, surface_url),
        })),
      );
  });

  it('reads a tree without a catalog or any listed surface as no data, unless ATLAS_DATA_DIR names it', () => {
    const empty = emptyTree();
    expect(publishedSurfacesIn(empty, false)).toEqual([]);
    expect(() => publishedSurfacesIn(empty, true)).toThrow(
      'has no catalog.json',
    );
    const catalogOnly = tree(
      CATALOG,
      CATALOG.artifacts.map(({ surface_url }) => surface_url),
    );
    expect(publishedSurfacesIn(catalogOnly, false)).toEqual([]);
    expect(() => publishedSurfacesIn(catalogOnly, true)).toThrow(
      `lists ${CATALOG.artifacts.length} of ${CATALOG.artifacts.length} surfaces`,
    );
  });

  it('refuses a tree that is missing one listed surface, with or without ATLAS_DATA_DIR', () => {
    const root = tree(CATALOG, [HBS_URL]);
    for (const mustHaveData of [false, true])
      expect(() => publishedSurfacesIn(root, mustHaveData)).toThrow(
        `lists 1 of ${CATALOG.artifacts.length} surfaces that the tree does not hold: hbs-rs334`,
      );
  });

  it('refuses a catalog that does not parse or repeats an id', () => {
    for (const catalog of [
      '{"artifacts": [',
      { artifacts: [{ id: 'hbs-rs334', surface_url: HBS_URL }] },
    ]) {
      const root = tree(catalog);
      for (const mustHaveData of [false, true])
        expect(() => publishedSurfacesIn(root, mustHaveData)).toThrow(
          'is not a valid Atlas catalog',
        );
    }
    const repeated = tree({
      ...CATALOG,
      artifacts: [...CATALOG.artifacts, CATALOG.artifacts[0]],
    });
    expect(() => publishedSurfacesIn(repeated, false)).toThrow(
      'lists an artifact id more than once',
    );
  });

  it('refuses a tree with data that does not list both full-grid artifacts', () => {
    const root = tree({
      ...CATALOG,
      artifacts: CATALOG.artifacts.filter(({ id }) => id !== 'cyt-il-6-174-c'),
    });
    for (const mustHaveData of [false, true])
      expect(() => publishedSurfacesIn(root, mustHaveData)).toThrow(
        'does not list cyt-il-6-174-c, so the full-grid suites cannot run',
      );
  });

  it('resolves the fixture directories and the default tree against the website', async () => {
    expect(GOLDEN_DIR).toBe(path.join(WEBSITE, 'tests/fixtures/atlas/golden'));
    expect(PARITY_DIR).toBe(path.join(WEBSITE, 'tests/fixtures/atlas/parity'));
    vi.stubEnv('ATLAS_DATA_DIR', '');
    vi.resetModules();
    const helper = await import('./helpers/atlas-geometry');
    expect(helper.ATLAS_DATA_ROOT).toBe(
      path.join(WEBSITE, 'public/data/atlas'),
    );
  });

  it('fails the import when ATLAS_DATA_DIR names a tree that lacks a listed surface', async () => {
    vi.stubEnv('ATLAS_DATA_DIR', tree(CATALOG, [HBS_URL]));
    vi.resetModules();
    await expect(import('./helpers/atlas-geometry')).rejects.toThrow(
      'surfaces that the tree does not hold: hbs-rs334',
    );
    vi.stubEnv('ATLAS_DATA_DIR', emptyTree());
    vi.resetModules();
    await expect(import('./helpers/atlas-geometry')).rejects.toThrow(
      'has no catalog.json',
    );
  });

  it('reads the ATLAS_DATA_DIR catalog once, at import', async () => {
    const root = tree();
    vi.stubEnv('ATLAS_DATA_DIR', path.relative(process.cwd(), root));
    vi.resetModules();
    const helper = await import('./helpers/atlas-geometry');
    expect(helper.ATLAS_DATA_ROOT).toBe(root);
    expect(helper.hasFullGrid).toBe(true);
    expect(helper.FULL_GRID_SURFACE).toBe(path.join(root, HBS_URL));
    rmSync(path.join(root, 'catalog.json'));
    expect(helper.publishedSurfaces()).toHaveLength(CATALOG.artifacts.length);
  });
});
