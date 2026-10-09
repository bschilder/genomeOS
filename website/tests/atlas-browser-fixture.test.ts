/** Unit tests for the Atlas browser fixture (fast-load design §B.8). */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import type { Page } from '@playwright/test';
import { describe, expect, it } from 'vitest';

import {
  artifactTierKey,
  corruptArtifactTier,
  delayArtifactTier,
  extractInlineCatalog,
  fetchedKeys,
  installAtlasBrowserFixture,
  readE2eCatalog,
  readE2eObject,
  urlMatchesKey,
  type FixtureCatalog,
} from './atlas-browser-fixture';

const websiteRoot = path.resolve(import.meta.dirname, '..');

const TINY: FixtureCatalog = {
  grids: { aaaa: { url: 'grids/h3-r3.aaaa.gosa' } },
  artifacts: [
    {
      id: 'hbs-rs334',
      model_version: 'v3',
      data_version: 'map-2026-08',
      surface_url: 'hbs-rs334.surface.json',
      observations_url: 'hbs-rs334.observations.json',
      downloads: {
        manifest: { url: 'hbs-rs334.manifest.json' },
        observations: { url: 'hbs-rs334.observations.json' },
        surface: { url: 'hbs-rs334.surface.json' },
      },
      web: {
        grid_sha256: 'aaaa',
        render: { url: 'surfaces/hbs-rs334/v3/map-2026-08/render.1111.gosa' },
        detail: { url: 'surfaces/hbs-rs334/v3/map-2026-08/detail.2222.gosa' },
      },
    },
    {
      id: 'no-observations',
      model_version: 'v1',
      data_version: 'd',
      surface_url: 'no-observations.surface.json',
      observations_url: null,
      downloads: {
        manifest: { url: 'no-observations.manifest.json' },
        observations: null,
        surface: { url: 'no-observations.surface.json' },
      },
      web: {
        grid_sha256: 'aaaa',
        render: { url: 'surfaces/no-observations/v1/d/render.3333.gosa' },
        detail: { url: 'surfaces/no-observations/v1/d/detail.4444.gosa' },
      },
    },
  ],
};

function appHtml(catalog: FixtureCatalog): string {
  const json = JSON.stringify(catalog).replaceAll('<', '\\u003c');
  return `<!doctype html><html><head><script type="application/json" id="atlas-catalog">${json}</script></head></html>`;
}

class FakeRoute {
  fallbacks = 0;
  fulfilled: { body?: Buffer; contentType?: string; status?: number }[] = [];
  readonly #url: string;
  constructor(url: string) {
    this.#url = url;
  }
  request() {
    return { url: () => this.#url };
  }
  async fallback() {
    this.fallbacks += 1;
  }
  async fulfill(options: {
    body?: Buffer;
    contentType?: string;
    status?: number;
  }) {
    this.fulfilled.push(options);
  }
  async abort() {}
}

type FakeHandler = (route: FakeRoute) => Promise<void> | void;

function fakePage(html: string) {
  const routes: { matcher: unknown; handler: FakeHandler }[] = [];
  const page = {
    request: {
      get: async () => ({
        ok: () => true,
        status: () => 200,
        text: async () => html,
      }),
    },
    route: async (matcher: unknown, handler: FakeHandler) => {
      routes.push({ matcher, handler });
    },
    unroute: async () => {},
  };
  return { page: page as unknown as Page, routes };
}

function handlerFor(
  routes: { matcher: unknown; handler: FakeHandler }[],
  url: string,
): FakeHandler {
  const match = [...routes]
    .reverse()
    .find(
      ({ matcher }) =>
        typeof matcher === 'function' &&
        (matcher as (value: URL) => boolean)(new URL(url)),
    );
  if (!match) throw new Error(`no route for ${url}`);
  return match.handler;
}

describe('fixture module boundary', () => {
  it('loads under plain Node type stripping and exports the helper surface', () => {
    const output = execFileSync(
      process.execPath,
      [
        '--no-warnings',
        '--input-type=module',
        '-e',
        "const m = await import('./tests/atlas-browser-fixture.ts'); console.log(Object.keys(m).sort().join(','));",
      ],
      { cwd: websiteRoot, encoding: 'utf8' },
    );
    expect(output.trim()).toBe(
      [
        'E2E_ARTIFACT_DATA_BASE',
        'E2E_CATALOG_PATH',
        'E2E_FIXTURE_DIR',
        'artifactTierKey',
        'corruptArtifactTier',
        'delayArtifactTier',
        'displayedArtifactIds',
        'extractInlineCatalog',
        'failArtifactTier',
        'fetchedKeys',
        'installAtlasBrowserFixture',
        'readE2eCatalog',
        'readE2eObject',
        'readInlineCatalog',
        'urlMatchesKey',
      ].join(','),
    );
  });

  it('imports only node built-ins and type-only Playwright', () => {
    const source = readFileSync(
      path.join(websiteRoot, 'tests/atlas-browser-fixture.ts'),
      'utf8',
    );
    const imports = [
      ...source.matchAll(/^import\s+(type\s+)?[\s\S]*?from\s+'([^']+)';/gm),
    ].map((match) => ({
      typeOnly: match[1] !== undefined,
      specifier: match[2],
    }));
    expect(imports.length).toBeGreaterThan(0);
    expect(
      imports.filter(
        ({ typeOnly, specifier }) =>
          !typeOnly && !specifier.startsWith('node:'),
      ),
    ).toEqual([]);
  });

  it('capture scripts pass only the served app URL', () => {
    for (const name of ['capture-atlas.mjs', 'capture-observation-studs.mjs']) {
      const script = readFileSync(
        path.join(websiteRoot, 'scripts', name),
        'utf8',
      );
      expect(script, name).toContain(
        'installAtlasBrowserFixture(page, { appUrl: `${baseUrl}/app/` })',
      );
      expect(script, name).not.toMatch(
        /surfaceScope|surfaceBudget|observationBudget|focus:/,
      );
    }
  });
});

describe('catalog helpers', () => {
  it('extracts the inline catalog including escaped <', () => {
    const catalog = extractInlineCatalog(
      appHtml({ ...TINY, grids: { aaaa: { url: 'grids/</script>.gosa' } } }),
    );
    expect(catalog.grids.aaaa?.url).toBe('grids/</script>.gosa');
    expect(() => extractInlineCatalog('<html></html>')).toThrow(
      'no inline <script id="atlas-catalog">',
    );
  });

  it('maps each tier to its catalog key and refuses missing data', () => {
    expect(artifactTierKey(TINY, 'hbs-rs334', 'grid')).toBe(
      'grids/h3-r3.aaaa.gosa',
    );
    expect(artifactTierKey(TINY, 'hbs-rs334', 'render')).toBe(
      'surfaces/hbs-rs334/v3/map-2026-08/render.1111.gosa',
    );
    expect(artifactTierKey(TINY, 'hbs-rs334', 'detail')).toBe(
      'surfaces/hbs-rs334/v3/map-2026-08/detail.2222.gosa',
    );
    expect(artifactTierKey(TINY, 'hbs-rs334', 'observations')).toBe(
      'hbs-rs334.observations.json',
    );
    expect(() => artifactTierKey(TINY, 'missing', 'render')).toThrow(
      'exactly one catalog artifact "missing", found 0',
    );
    expect(() =>
      artifactTierKey(TINY, 'no-observations', 'observations'),
    ).toThrow('"no-observations" has no observations');
    expect(fetchedKeys(TINY)).toEqual([
      'grids/h3-r3.aaaa.gosa',
      'hbs-rs334.observations.json',
      'surfaces/hbs-rs334/v3/map-2026-08/detail.2222.gosa',
      'surfaces/hbs-rs334/v3/map-2026-08/render.1111.gosa',
      'surfaces/no-observations/v1/d/detail.4444.gosa',
      'surfaces/no-observations/v1/d/render.3333.gosa',
    ]);
  });

  it('matches a key at the end of any base', () => {
    const key = 'surfaces/hbs-rs334/v3/map-2026-08/render.1111.gosa';
    expect(
      urlMatchesKey(new URL(`http://127.0.0.1:4322/data/atlas/${key}`), key),
    ).toBe(true);
    expect(
      urlMatchesKey(new URL(`https://cdn.example/atlas/web/${key}`), key),
    ).toBe(true);
    expect(
      urlMatchesKey(
        new URL(
          'http://127.0.0.1:4322/data/atlas/surfaces/g6pd/v3/map-2026-08/render.1111.gosa',
        ),
        key,
      ),
    ).toBe(false);
  });
});

describe('committed e2e tree', () => {
  it('has an object for every key the e2e catalog fetches', () => {
    const catalog = readE2eCatalog();
    expect(catalog.artifacts).toHaveLength(30);
    const keys = fetchedKeys(catalog);
    expect(keys).toHaveLength(91);
    for (const key of keys)
      expect(readE2eObject(key).byteLength, key).toBeGreaterThan(0);
  });

  it('refuses a served page that does not inline the e2e catalog', async () => {
    const { page } = fakePage(appHtml(TINY));
    await expect(
      installAtlasBrowserFixture(page, {
        appUrl: 'http://fixture.invalid/app/a',
      }),
    ).rejects.toThrow('npm run build:e2e');
  });

  it('fulfils catalog keys from the tree', async () => {
    const catalog = readE2eCatalog();
    const { page, routes } = fakePage(appHtml(catalog));
    await installAtlasBrowserFixture(page, {
      appUrl: 'http://fixture.invalid/app/b',
    });
    const key = artifactTierKey(catalog, 'hbs-rs334', 'render');
    const route = new FakeRoute(`http://127.0.0.1:4322/data/atlas/${key}`);
    await handlerFor(routes, route.request().url())(route);
    expect(route.fulfilled).toHaveLength(1);
    expect(route.fulfilled[0]?.contentType).toBe('application/octet-stream');
    expect(route.fulfilled[0]?.body?.equals(readE2eObject(key))).toBe(true);
  });
});

describe('tier overrides', () => {
  it('holds a delayed tier until release and counts hits', async () => {
    const { page, routes } = fakePage(appHtml(TINY));
    const delay = await delayArtifactTier(
      page,
      'hbs-rs334',
      'render',
      Number.POSITIVE_INFINITY,
      {
        appUrl: 'http://fixture.invalid/app/c',
      },
    );
    const route = new FakeRoute(
      'http://127.0.0.1:4322/data/atlas/surfaces/hbs-rs334/v3/map-2026-08/render.1111.gosa',
    );
    const pending = handlerFor(routes, route.request().url())(route);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(delay.hits()).toBe(1);
    expect(route.fallbacks).toBe(0);
    delay.release();
    await pending;
    expect(route.fallbacks).toBe(1);
    const later = new FakeRoute(route.request().url());
    await handlerFor(routes, later.request().url())(later);
    expect(delay.hits()).toBe(2);
    expect(later.fallbacks).toBe(1);
  });

  it('releases a finite delay on its own', async () => {
    const { page, routes } = fakePage(appHtml(TINY));
    await delayArtifactTier(page, 'hbs-rs334', 'observations', 20, {
      appUrl: 'http://fixture.invalid/app/d',
    });
    const route = new FakeRoute(
      'http://127.0.0.1:4322/data/atlas/hbs-rs334.observations.json',
    );
    const started = Date.now();
    await handlerFor(routes, route.request().url())(route);
    expect(Date.now() - started).toBeGreaterThanOrEqual(15);
    expect(route.fallbacks).toBe(1);
  });

  it('serves a corrupted copy of an e2e object', async () => {
    const catalog = readE2eCatalog();
    const { page, routes } = fakePage(appHtml(catalog));
    const corruption = await corruptArtifactTier(page, 'hbs-rs334', 'render', {
      appUrl: 'http://fixture.invalid/app/e',
    });
    const key = artifactTierKey(catalog, 'hbs-rs334', 'render');
    const route = new FakeRoute(`http://127.0.0.1:4322/data/atlas/${key}`);
    await handlerFor(routes, route.request().url())(route);
    const original = readE2eObject(key);
    const served = route.fulfilled[0]?.body;
    expect(corruption.hits()).toBe(1);
    expect(served?.byteLength).toBe(original.byteLength);
    expect(served?.subarray(0, -1).equals(original.subarray(0, -1))).toBe(true);
    expect(served?.at(-1)).toBe((original.at(-1) ?? 0) ^ 0xff);
  });
});
