/**
 * Opt-in full-size Atlas data checks (fast-load design §B.8, §C.3).
 *
 *   ATLAS_DATA_DIR=public/data/atlas npx vitest run tests/atlas-data-dir.test.ts
 *
 * Moved from site.spec.ts, whose browser tests now run on the compact e2e catalog.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  atlasCatalogSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
} from '../src/atlas/contracts';
import { decodeGrid, decodeRender } from '../src/atlas/gosa/decode';

const dataDirectory = process.env.ATLAS_DATA_DIR
  ? path.resolve(process.env.ATLAS_DATA_DIR)
  : null;

function readBytes(directory: string, key: string): ArrayBuffer {
  const bytes = readFileSync(path.join(directory, key));
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

function readJson(directory: string, key: string): unknown {
  return JSON.parse(readFileSync(path.join(directory, key), 'utf8'));
}

describe.skipIf(dataDirectory === null)(
  'full-size Atlas data (ATLAS_DATA_DIR)',
  () => {
    it('holds the complete HbS grid, render tier, surface and observations', () => {
      const directory = dataDirectory as string;
      const catalog = atlasCatalogSchema.parse(
        readJson(directory, 'catalog.json'),
      );
      expect(catalog.artifacts).toHaveLength(30);
      const hbs = catalog.artifacts.find(({ id }) => id === 'hbs-rs334');
      if (hbs === undefined)
        throw new Error('hbs-rs334 is missing from the catalog');
      expect(hbs.n_cells).toBe(77_844);
      expect(hbs.n_observations).toBe(1_071);

      const entry = catalog.grids[hbs.web.grid_sha256];
      if (entry === undefined) throw new Error('the HbS grid entry is missing');
      const grid = decodeGrid(readBytes(directory, entry.url), {
        gridSha256: hbs.web.grid_sha256,
        entry,
      });
      expect(grid.n).toBe(77_844);
      const render = decodeRender(readBytes(directory, hbs.web.render.url), {
        ref: hbs,
        grid,
      });
      expect(render.support).toHaveLength(77_844);
      expect(render.post_mean).toHaveLength(77_844);

      const surface = surfaceArtifactSchema.parse(
        readJson(directory, hbs.surface_url),
      );
      expect(surface.cells).toHaveLength(77_844);
      if (hbs.observations_url === null)
        throw new Error('HbS has no observations');
      const observations = observationArtifactSchema.parse(
        readJson(directory, hbs.observations_url),
      );
      expect(observations.observations).toHaveLength(1_071);
    }, 60_000);
  },
);
