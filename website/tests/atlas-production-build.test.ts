/** Unit tests for the performance specs' production-build guard (fast-load design §B.1, §C.2). */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { assertProductionBuild } from './support/production-build';

const BASE_URL = 'http://127.0.0.1:4322';
const websiteRoot = path.resolve(import.meta.dirname, '..');

interface CatalogJson {
  grids: Record<string, unknown>;
  artifacts: {
    id: string;
    model_version: string;
    data_version: string;
    surface_url: string;
    observations_url: string | null;
    downloads: Record<string, { sha256: string; url: string } | null>;
    web: { render: { sha256: string; url: string } };
  }[];
}

const readCatalog = (relative: string): CatalogJson =>
  JSON.parse(
    readFileSync(path.join(websiteRoot, relative), 'utf8'),
  ) as CatalogJson;
const production = (): CatalogJson =>
  readCatalog('public/data/atlas/catalog.json');

function serve(catalog: unknown, status = 200): void {
  const json = JSON.stringify(catalog).replace(/</g, '\\u003c');
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          `<!doctype html><script type="application/json" id="atlas-catalog">${json}</script>`,
          { status },
        ),
    ),
  );
}

/** What Part C's `encode_atlas_web.py --with-downloads` does to the catalog (design §C.2). */
function withBucketDownloadKeys(catalog: CatalogJson): CatalogJson {
  for (const artifact of catalog.artifacts) {
    for (const [kind, entry] of Object.entries(artifact.downloads)) {
      if (entry === null) continue;
      entry.url = `downloads/${artifact.id}/${artifact.model_version}/${artifact.data_version}/${artifact.id}.${kind}.${entry.sha256.slice(0, 16)}.json`;
    }
    artifact.surface_url = artifact.downloads.surface!.url;
    if (artifact.observations_url !== null)
      artifact.observations_url = artifact.downloads.observations!.url;
  }
  return catalog;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('assertProductionBuild', () => {
  it('accepts /app/ when it inlines the repository catalog', async () => {
    serve(production());
    await expect(assertProductionBuild(BASE_URL)).resolves.toEqual(
      production(),
    );
  });

  it('accepts the staged catalog, whose JSON downloads sit at bucket keys', async () => {
    const staged = withBucketDownloadKeys(production());
    expect(staged.artifacts[0].surface_url).not.toBe(
      production().artifacts[0].surface_url,
    );
    serve(staged);
    await expect(assertProductionBuild(BASE_URL)).resolves.toEqual(staged);
  });

  it('rejects a subset catalog on the production grid', async () => {
    const subset = production();
    subset.artifacts = subset.artifacts.slice(0, 2);
    serve(subset);
    await expect(assertProductionBuild(BASE_URL)).rejects.toThrow(
      /does not inline public\/data\/atlas\/catalog\.json \(artifacts differ\)/,
    );
  });

  it('rejects a stale build whose render tier is not the repository one', async () => {
    const stale = production();
    stale.artifacts[1].web.render = {
      ...stale.artifacts[1].web.render,
      sha256: '0'.repeat(64),
      url: 'surfaces/g6pd-deficiency/v3/map-2026-08/render.0000000000000000.gosa',
    };
    serve(stale);
    await expect(assertProductionBuild(BASE_URL)).rejects.toThrow(
      /\(artifacts differ\)/,
    );
  });

  it('rejects a stale build with a different canonical JSON file', async () => {
    const stale = production();
    stale.artifacts[0].downloads.surface!.sha256 = '0'.repeat(64);
    serve(stale);
    await expect(assertProductionBuild(BASE_URL)).rejects.toThrow(
      /\(artifacts differ\)/,
    );
  });

  it('rejects the e2e build', async () => {
    serve(readCatalog('tests/fixtures/atlas/e2e/catalog.json'));
    await expect(assertProductionBuild(BASE_URL)).rejects.toThrow(
      /does not inline public\/data\/atlas\/catalog\.json \(.*grids.*\)\. Performance specs measure full data/,
    );
  });

  it('rejects a failed /app/ response', async () => {
    serve(production(), 404);
    await expect(assertProductionBuild(BASE_URL)).rejects.toThrow(
      'GET http://127.0.0.1:4322/app/ returned HTTP 404.',
    );
  });
});
