import { describe, expect, it } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import { INLINE_CATALOG_ID } from '../src/atlas/inline-catalog';
import { preloadScriptSource } from '../src/atlas/preload-script';
import { parseExplorerState } from '../src/atlas/url-state';
import { resolveDataUrl } from '../src/lib/data-url';
import { goldenCatalog, goldenCatalogRaw } from './support/gosa-builder';

interface FakeLink {
  as?: string;
  crossOrigin?: string;
  href?: string;
  rel?: string;
}

const BASE_URI = 'https://genome-os.org/genomeOS/app/';
const catalog = goldenCatalog();

function runPreload(options: {
  base?: string;
  catalogText?: string | null;
  search?: string;
}): FakeLink[] {
  const links: FakeLink[] = [];
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
  new Function('document', 'location', preloadScriptSource())(document, {
    search: options.search ?? '',
  });
  return links;
}

function expectedKeys(ref: ArtifactRef): string[] {
  return [
    catalog.grids[ref.web.grid_sha256].url,
    ref.web.render.url,
    ...(ref.observations_available ? [ref.observations_url] : []),
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
