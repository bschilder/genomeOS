import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  escapeInlineJson,
  INLINE_CATALOG_ID,
  readInlineCatalog,
} from '../src/atlas/inline-catalog';
import {
  DEFAULT_ATLAS_CATALOG_PATH,
  loadPageCatalog,
} from '../src/lib/catalog-build';
import { GOLDEN_DIR, goldenCatalogRaw } from './support/gosa-builder';

function documentWith(text: string | null): Pick<Document, 'getElementById'> {
  return {
    getElementById: (id: string) =>
      id === INLINE_CATALOG_ID && text !== null
        ? ({ textContent: text } as HTMLElement)
        : null,
  };
}

describe('escapeInlineJson', () => {
  it('removes every "<" so the JSON cannot close its script element', () => {
    const hostile = { note: '</script><script>alert(1)</script><!--' };
    const escaped = escapeInlineJson(JSON.stringify(hostile));
    expect(escaped).not.toContain('<');
    expect(JSON.parse(escaped)).toEqual(hostile);
  });
});

describe('readInlineCatalog', () => {
  it('parses the inline catalog element', () => {
    expect(readInlineCatalog(documentWith('{"schema_version":1}'))).toEqual({
      schema_version: 1,
    });
  });

  it('returns undefined when the element is missing or is not JSON', () => {
    expect(readInlineCatalog(documentWith(null))).toBeUndefined();
    expect(readInlineCatalog(documentWith('{oops'))).toBeUndefined();
  });
});

describe('loadPageCatalog', () => {
  it('defaults to the public catalog', () => {
    expect(DEFAULT_ATLAS_CATALOG_PATH).toBe('public/data/atlas/catalog.json');
  });

  it('validates a catalog and returns escaped, unchanged JSON', () => {
    const { json } = loadPageCatalog(path.join(GOLDEN_DIR, 'catalog.json'));
    expect(json).not.toContain('<');
    expect(JSON.parse(json)).toEqual(goldenCatalogRaw());
  });

  it('fails loudly on a catalog that violates the strict schema', () => {
    const directory = mkdtempSync(path.join(tmpdir(), 'genomeos-catalog-'));
    try {
      const broken = path.join(directory, 'catalog.json');
      writeFileSync(broken, JSON.stringify({ schema_version: 1 }));
      expect(() => loadPageCatalog(broken)).toThrow(/fails atlasCatalogSchema/);
      writeFileSync(broken, '{oops');
      expect(() => loadPageCatalog(broken)).toThrow(
        /could not be read as JSON/,
      );
    } finally {
      rmSync(directory, { force: true, recursive: true });
    }
  });

  it('resolves a relative path against the website directory', () => {
    const websiteRoot = path.resolve(import.meta.dirname, '..');
    const relative = path.relative(
      websiteRoot,
      path.join(GOLDEN_DIR, 'catalog.json'),
    );
    expect(() => loadPageCatalog(relative, websiteRoot)).not.toThrow();
  });
});
