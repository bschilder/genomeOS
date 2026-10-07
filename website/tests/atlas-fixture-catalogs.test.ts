import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { atlasCatalogSchema } from '../src/atlas/contracts';

/**
 * Committed Atlas fixture trees (fast-load spec §B.5, §B.8) and the catalog keys each one ships.
 * `objects` are the grid, render and detail GOSA objects; the other keys name the JSON files the
 * tree carries. Keys a tree does not ship name the full canonical artifact it was cut from.
 */
const TREES = {
  golden: ['objects', 'observations', 'surface', 'downloads'],
} as const satisfies Record<
  string,
  readonly ('objects' | 'observations' | 'surface' | 'downloads')[]
>;

const fixtureRoot = fileURLToPath(
  new URL('./fixtures/atlas/', import.meta.url),
);

function stat(tree: string, key: string): { bytes: number; sha256: string } {
  const bytes = readFileSync(`${fixtureRoot}${tree}/${key}`);
  return {
    bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'),
  };
}

describe.each(Object.entries(TREES))('%s fixture tree', (tree, shipped) => {
  const catalog = () =>
    atlasCatalogSchema.parse(
      JSON.parse(readFileSync(`${fixtureRoot}${tree}/catalog.json`, 'utf8')),
    );

  it('passes the strict catalog contract with exactly one grid', () => {
    expect(Object.keys(catalog().grids)).toHaveLength(1);
  });

  it('ships every declared object with its digest and decoded size', () => {
    const parsed = catalog();
    const has = (part: (typeof shipped)[number]) =>
      (shipped as readonly string[]).includes(part);
    for (const entry of Object.values(parsed.grids))
      expect(stat(tree, entry.url)).toEqual({
        bytes: entry.bytes,
        sha256: entry.sha256,
      });
    for (const artifact of parsed.artifacts) {
      for (const object of [artifact.web.render, artifact.web.detail])
        expect(stat(tree, object.url), object.url).toEqual({
          bytes: object.bytes,
          sha256: object.sha256,
        });
      if (has('observations') && artifact.observations_available)
        expect(stat(tree, artifact.observations_url)).toEqual({
          bytes: artifact.observations_bytes,
          sha256: artifact.observations_sha256,
        });
      if (has('surface'))
        expect(stat(tree, artifact.surface_url).sha256).toBe(
          artifact.surface_sha256,
        );
      if (has('downloads'))
        for (const download of Object.values(artifact.downloads))
          if (download)
            expect(stat(tree, download.url).sha256, download.url).toBe(
              download.sha256,
            );
    }
  });
});
