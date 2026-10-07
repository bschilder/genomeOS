import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { atlasCatalogSchema } from '../src/atlas/contracts';
import {
  decodeDetail,
  decodeGrid,
  decodeRender,
} from '../src/atlas/gosa/decode';
import {
  fixtureBytes,
  GOLDEN_DIR,
  onlyGrid,
  toBuffer,
} from './support/gosa-builder';

/**
 * The committed trees whose digests atlas-fixture-catalogs.test.ts checks; here the browser's own
 * decoder reads every object (fast-load design §B.8).
 */
const TREES = {
  e2e: path.resolve(import.meta.dirname, 'fixtures/atlas/e2e'),
  golden: GOLDEN_DIR,
  parity: path.resolve(import.meta.dirname, 'fixtures/atlas/parity'),
};

describe.each(Object.entries(TREES))(
  '%s fixture tree in the TS decoder',
  (_name, directory) => {
    const catalog = atlasCatalogSchema.parse(
      JSON.parse(readFileSync(path.join(directory, 'catalog.json'), 'utf8')),
    );
    const { entry, gridSha256 } = onlyGrid(catalog);
    const grid = decodeGrid(toBuffer(fixtureBytes(directory, entry.url)), {
      entry,
      gridSha256,
    });

    it('decodes the shared grid at its declared size', () => {
      expect(grid.n).toBe(entry.n_cells);
      expect(grid.resolution).toBe(entry.resolution);
    });

    it.each(catalog.artifacts.map((ref) => [ref.id, ref] as const))(
      '%s render and detail tiers decode and bind to the catalog',
      (_id, ref) => {
        const render = decodeRender(
          toBuffer(fixtureBytes(directory, ref.web.render.url)),
          {
            grid,
            ref,
          },
        );
        const detail = decodeDetail(
          toBuffer(fixtureBytes(directory, ref.web.detail.url)),
          {
            grid,
            ref,
            render,
          },
        );
        expect(render.support).toHaveLength(ref.n_cells);
        expect(detail.post_mean).toHaveLength(ref.n_cells);
      },
    );
  },
);
