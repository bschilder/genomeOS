import { describe, expect, it } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import {
  INLINE_CATALOG_ID,
  SURFACE_DOWNLOADS_AFTER_SCENE,
  SURFACE_DOWNLOADS_ATTRIBUTE,
  surfaceDownloadsAfterScene,
} from '../src/atlas/inline-catalog';
import { preloadScriptSource } from '../src/atlas/preload-script';
import { parseExplorerState } from '../src/atlas/url-state';
import { resolveDataUrl } from '../src/lib/data-url';
import { goldenCatalog, goldenCatalogRaw } from './support/gosa-builder';

interface FakeLink {
  as?: string;
  crossOrigin?: string;
  fetchPriority?: string;
  href?: string;
  rel?: string;
}

interface FakeConnection {
  effectiveType?: string;
  saveData?: boolean;
}

const BASE_URI = 'https://genome-os.org/genomeOS/app/';
const catalog = goldenCatalog();

function runPreload(options: {
  base?: string;
  catalogText?: string | null;
  /** `navigator.connection`; null runs without one (Safari, Firefox). */
  connection?: FakeConnection | null;
  search?: string;
  /** Receives the attributes the script sets on the catalog element. */
  attributes?: Map<string, string>;
}): FakeLink[] {
  const links: FakeLink[] = [];
  const attributes = options.attributes ?? new Map<string, string>();
  const base = options.base ?? '/genomeOS/data/atlas/';
  const text =
    options.catalogText === undefined
      ? JSON.stringify(goldenCatalogRaw())
      : options.catalogText;
  const element =
    text === null
      ? null
      : {
          getAttribute: (name: string) =>
            name === 'data-artifact-data-base' ? base : null,
          setAttribute: (name: string, value: string) =>
            attributes.set(name, value),
          textContent: text,
        };
  const document = {
    baseURI: BASE_URI,
    createElement: (tag: string) => {
      expect(tag).toBe('link');
      return {} as FakeLink;
    },
    getElementById: (id: string) => (id === INLINE_CATALOG_ID ? element : null),
    head: {
      appendChild: (link: FakeLink) => {
        links.push(link);
        return link;
      },
    },
  };
  const connection =
    options.connection === undefined
      ? { effectiveType: '4g', saveData: false }
      : options.connection;
  new Function('document', 'location', 'navigator', preloadScriptSource())(
    document,
    { search: options.search ?? '' },
    connection === null ? {} : { connection },
  );
  return links;
}

/** Observations first (the first frame), then the grid and render tiers. */
function expectedKeys(ref: ArtifactRef): string[] {
  return [
    ...(ref.observations_available ? [ref.observations_url] : []),
    catalog.grids[ref.web.grid_sha256].url,
    ref.web.render.url,
  ];
}

describe('preloadScriptSource', () => {
  it('preloads the default artifact with fetch-matching links', () => {
    const base = '/genomeOS/data/atlas/';
    const links = runPreload({ base });
    expect(links.map(({ href }) => href)).toEqual(
      expectedKeys(catalog.artifacts[0]).map((key) =>
        resolveDataUrl(key, base, BASE_URI),
      ),
    );
    for (const link of links) {
      expect(link).toMatchObject({
        as: 'fetch',
        crossOrigin: 'anonymous',
        rel: 'preload',
      });
    }
  });

  it('preloads the observations at high priority and the surface tiers at low priority', () => {
    // Fast-load design §B.1, ruling R84-slow4g; the provider fetches each tier at the same
    // priority, so the fetch reuses the preload.
    const ref = catalog.artifacts[0];
    expect(ref.observations_available).toBe(true);
    const links = runPreload({});
    expect(links.map(({ fetchPriority }) => fetchPriority)).toEqual([
      'high',
      'low',
      'low',
    ]);
    expect(links[0].href).toBe(
      resolveDataUrl(ref.observations_url!, '/genomeOS/data/atlas/', BASE_URI),
    );
  });

  it.each([
    ['3g (the DevTools Slow 4G preset)', { effectiveType: '3g' }],
    ['2g', { effectiveType: '2g' }],
    ['slow-2g', { effectiveType: 'slow-2g' }],
    ['Save-Data', { effectiveType: '4g', saveData: true }],
  ])(
    'leaves the render tier for after the scene chunk on %s',
    (_label, connection) => {
      const attributes = new Map<string, string>();
      const links = runPreload({ attributes, connection });
      const ref = catalog.artifacts[0];
      expect(links.map(({ href }) => href)).toEqual(
        expectedKeys(ref)
          .slice(0, 2)
          .map((key) => resolveDataUrl(key, '/genomeOS/data/atlas/', BASE_URI)),
      );
      expect(links.map(({ fetchPriority }) => fetchPriority)).toEqual([
        'high',
        'low',
      ]);
      expect(attributes.get(SURFACE_DOWNLOADS_ATTRIBUTE)).toBe(
        SURFACE_DOWNLOADS_AFTER_SCENE,
      );
    },
  );

  it.each([
    ['4g', { effectiveType: '4g', saveData: false }],
    ['no navigator.connection', null],
  ])('preloads every tier on %s', (_label, connection) => {
    const attributes = new Map<string, string>();
    expect(runPreload({ attributes, connection })).toHaveLength(3);
    expect(attributes.size).toBe(0);
  });

  it('preloads the artifact the shared link selects, as the explorer does', () => {
    const selected = catalog.artifacts[catalog.artifacts.length - 1];
    const search = `?entity=${selected.id}&metric=post_sd`;
    expect(parseExplorerState(search, catalog).state.entityId).toBe(
      selected.id,
    );
    expect(runPreload({ search }).map(({ href }) => href)).toEqual(
      expectedKeys(selected).map((key) =>
        resolveDataUrl(key, '/genomeOS/data/atlas/', BASE_URI),
      ),
    );
  });

  it('preloads nothing for an unavailable entity', () => {
    expect(
      parseExplorerState('?entity=missing', catalog).corrections.some(
        ({ field }) => field === 'entity',
      ),
    ).toBe(true);
    expect(runPreload({ search: '?entity=missing' })).toEqual([]);
  });

  it('skips observations that are declared unavailable', () => {
    const raw = goldenCatalogRaw() as { artifacts: Record<string, unknown>[] };
    raw.artifacts[0] = {
      ...raw.artifacts[0],
      observations_available: false,
      observations_url: null,
    };
    expect(runPreload({ catalogText: JSON.stringify(raw) })).toHaveLength(2);
  });

  it('uses absolute hrefs for an absolute artifact base', () => {
    const base = 'https://storage.googleapis.com/example-bucket/atlas/web/';
    expect(runPreload({ base }).map(({ href }) => href)).toEqual(
      expectedKeys(catalog.artifacts[0]).map((key) => `${base}${key}`),
    );
  });

  it('never throws on a missing or malformed catalog', () => {
    expect(runPreload({ catalogText: null })).toEqual([]);
    expect(runPreload({ catalogText: '{oops' })).toEqual([]);
  });

  it('is a classic inline script that cannot close its element', () => {
    const source = preloadScriptSource();
    expect(source).not.toMatch(/^\s*(import|export)\b/m);
    expect(source).not.toContain('</script');
    expect(source).toContain(JSON.stringify(INLINE_CATALOG_ID));
  });
});

describe('surfaceDownloadsAfterScene', () => {
  it('reads the head script decision from the catalog element', () => {
    const doc = (value: string | null) => ({
      getElementById: (id: string) =>
        id === INLINE_CATALOG_ID
          ? ({ getAttribute: () => value } as unknown as HTMLElement)
          : null,
    });
    expect(surfaceDownloadsAfterScene(doc(SURFACE_DOWNLOADS_AFTER_SCENE))).toBe(
      true,
    );
    expect(surfaceDownloadsAfterScene(doc(null))).toBe(false);
    expect(surfaceDownloadsAfterScene({ getElementById: () => null })).toBe(
      false,
    );
  });
});
