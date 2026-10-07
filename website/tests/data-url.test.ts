import { describe, expect, it } from 'vitest';

import { resolveInternalTarget } from '../scripts/check-links.mjs';
import { dataKeySchema } from '../src/atlas/contracts';
import {
  assertDataBase,
  assertDataKey,
  dataHref,
  dataOrigin,
  resolveDataUrl,
} from '../src/lib/data-url';

const RENDER_KEY =
  'surfaces/hbs-rs334/v3/map-2026-08/render.0123456789abcdef.gosa';
const GRID_KEY = 'grids/h3-r4.0123456789abcdef.gosa';
const BUCKET_BASE = 'https://storage.googleapis.com/example-bucket/atlas/web/';
const LOCAL_BASE = 'http://127.0.0.1:4323/';
const DOC_BASE = 'https://genome-os.org/genomeOS/app/?entity=hbs-rs334';

// Each starts with "/" or "https://" and ends in "/", so a prefix test accepts it, but the URL
// parser reads a different URL from the one written: a backslash reads as "/", tabs and newlines
// are stripped, a query or fragment is dropped on resolution, "user@" moves the host and ".."
// leaves the directory (or the bucket).
const HOSTILE_BASES = [
  '/\\evil.example/',
  '/\t/evil.example/',
  '/\n/evil.example/',
  '/data/atlas/?v=1/',
  '/data/atlas/#/',
  '/data/../atlas/',
  `${BUCKET_BASE}?v=1/`,
  `${BUCKET_BASE}#/`,
  'https://user:secret@storage.googleapis.com/example-bucket/atlas/web/',
  'https://storage.googleapis.com@evil.example/atlas/web/',
  'https://storage.googleapis.com/example-bucket/../atlas/web/',
  'https://storage.googleapis.com\\evil.example/',
];

const ACCEPTED_KEYS = [
  RENDER_KEY,
  GRID_KEY,
  'hbs-rs334.surface.json',
  'external/gnomad/chr11-5227002-t-a.json',
  'ne-50m-admin-0.geojson',
];
const REJECTED_KEYS = [
  '',
  '/grids/h3-r4.gosa',
  '../catalog.json',
  'grids/../../secret.gosa',
  'https://example.org/x.gosa',
  '//example.org/x.gosa',
  'Grids/H3-R4.gosa',
  'grids/h3-r4.gosa?v=1',
  '.hidden/x.gosa',
];

function throws(run: () => void): boolean {
  try {
    run();
    return false;
  } catch {
    return true;
  }
}

describe('resolveDataUrl', () => {
  it('resolves the root deployment base against the document', () => {
    expect(
      resolveDataUrl(
        RENDER_KEY,
        '/data/atlas/',
        'http://127.0.0.1:4322/app/?entity=hbs-rs334',
      ),
    ).toBe(`http://127.0.0.1:4322/data/atlas/${RENDER_KEY}`);
  });

  it('keeps the /genomeOS/ project base', () => {
    expect(
      resolveDataUrl(
        GRID_KEY,
        '/genomeOS/data/atlas/',
        'https://bschilder.github.io/genomeOS/app/',
      ),
    ).toBe(`https://bschilder.github.io/genomeOS/data/atlas/${GRID_KEY}`);
  });

  it('ignores the document origin for an absolute base', () => {
    expect(
      resolveDataUrl(RENDER_KEY, BUCKET_BASE, 'https://genome-os.org/app/'),
    ).toBe(`${BUCKET_BASE}${RENDER_KEY}`);
  });

  it('refuses an absolute base without a trailing slash', () => {
    expect(() =>
      resolveDataUrl(
        RENDER_KEY,
        BUCKET_BASE.slice(0, -1),
        'https://genome-os.org/app/',
      ),
    ).toThrow('Atlas data base must end in "/"');
  });

  it('resolves the local fixture origin as an absolute base', () => {
    expect(resolveDataUrl(GRID_KEY, LOCAL_BASE, DOC_BASE)).toBe(
      `${LOCAL_BASE}${GRID_KEY}`,
    );
  });

  it.each(REJECTED_KEYS)('refuses the key %j', (key) => {
    expect(() => resolveDataUrl(key, '/data/atlas/', DOC_BASE)).toThrow(
      /Atlas data key/,
    );
    expect(() => resolveDataUrl(key, BUCKET_BASE, DOC_BASE)).toThrow(
      /Atlas data key/,
    );
  });

  it.each(HOSTILE_BASES)('refuses the hostile base %j', (base) => {
    expect(() => resolveDataUrl(GRID_KEY, base, DOC_BASE)).toThrow(
      /Atlas data base/,
    );
  });
});

describe('assertDataBase', () => {
  it.each([
    '/data/atlas/',
    '/genomeOS/data/atlas/',
    BUCKET_BASE,
    'http://localhost:4323/',
    'http://127.0.0.1:4323/',
  ])('accepts %s', (base) => {
    expect(() => assertDataBase(base)).not.toThrow();
  });

  it.each([
    'data/atlas/',
    '//cdn.example.org/atlas/',
    'http://cdn.example.org/atlas/',
    'http://localhost.example.org/atlas/',
    'ftp://cdn.example.org/atlas/',
    '/data/atlas',
  ])('rejects %s', (base) => {
    expect(() => assertDataBase(base)).toThrow(/Atlas data base/);
  });

  it.each(HOSTILE_BASES)(
    'rejects %j, which leaves the base once parsed',
    (base) => {
      expect(() => assertDataBase(base)).toThrow(
        /root-relative or an absolute https URL/,
      );
    },
  );

  it('does not need URL.canParse (Safari before 17, Chrome before 120)', () => {
    const canParse = Object.getOwnPropertyDescriptor(URL, 'canParse');
    Reflect.deleteProperty(URL, 'canParse');
    try {
      expect(() => assertDataBase(BUCKET_BASE)).not.toThrow();
      expect(() => assertDataBase(LOCAL_BASE)).not.toThrow();
      expect(resolveDataUrl(GRID_KEY, BUCKET_BASE, DOC_BASE)).toBe(
        `${BUCKET_BASE}${GRID_KEY}`,
      );
      expect(() => assertDataBase('https://user@example.org/')).toThrow(
        /Atlas data base/,
      );
    } finally {
      if (canParse !== undefined) {
        Object.defineProperty(URL, 'canParse', canParse);
      }
    }
  });
});

describe('assertDataKey', () => {
  it.each(ACCEPTED_KEYS)('accepts %s', (key) => {
    expect(() => assertDataKey(key)).not.toThrow();
  });

  it.each(REJECTED_KEYS)('rejects %j', (key) => {
    expect(() => assertDataKey(key)).toThrow(/Atlas data key/);
  });

  it('agrees with the catalog dataKeySchema on every case', () => {
    for (const key of [...ACCEPTED_KEYS, ...REJECTED_KEYS]) {
      expect(dataKeySchema.safeParse(key).success, key).toBe(
        !throws(() => assertDataKey(key)),
      );
    }
  });
});

describe('dataHref', () => {
  it('emits a root-relative href for a root-relative base', () => {
    expect(dataHref('hbs-rs334.surface.json', '/data/atlas/')).toBe(
      '/data/atlas/hbs-rs334.surface.json',
    );
    expect(dataHref(GRID_KEY, '/genomeOS/data/atlas/')).toBe(
      `/genomeOS/data/atlas/${GRID_KEY}`,
    );
  });

  it('emits the absolute URL for an absolute base', () => {
    expect(dataHref(RENDER_KEY, BUCKET_BASE)).toBe(
      `${BUCKET_BASE}${RENDER_KEY}`,
    );
  });

  it('stays inside the deployment base that check-links enforces', () => {
    expect(
      resolveInternalTarget(
        dataHref(GRID_KEY, '/genomeOS/data/atlas/'),
        'app/index.html',
        '/genomeOS/',
      ),
    ).toBe(`data/atlas/${GRID_KEY}`);
    expect(
      resolveInternalTarget(
        dataHref(GRID_KEY, '/data/atlas/'),
        'app/index.html',
        '/',
      ),
    ).toBe(`data/atlas/${GRID_KEY}`);
    expect(
      resolveInternalTarget(
        dataHref(GRID_KEY, BUCKET_BASE),
        'app/index.html',
        '/',
      ),
    ).toBeNull();
  });

  it.each(['/data/atlas/', '/genomeOS/data/atlas/', BUCKET_BASE, LOCAL_BASE])(
    'resolves to the fetch URL for base %s',
    (base) => {
      const docBase = 'https://genome-os.org/genomeOS/app/?entity=hbs-rs334';
      expect(new URL(dataHref(RENDER_KEY, base), docBase).href).toBe(
        resolveDataUrl(RENDER_KEY, base, docBase),
      );
    },
  );

  it.each(REJECTED_KEYS)('refuses the key %j', (key) => {
    expect(() => dataHref(key, '/data/atlas/')).toThrow(/Atlas data key/);
    expect(() => dataHref(key, BUCKET_BASE)).toThrow(/Atlas data key/);
  });

  it.each(HOSTILE_BASES)('refuses the hostile base %j', (base) => {
    expect(() => dataHref(GRID_KEY, base)).toThrow(/Atlas data base/);
  });
});

describe('dataOrigin', () => {
  it('names a preconnect origin only for an absolute base', () => {
    expect(dataOrigin('/data/atlas/')).toBeNull();
    expect(dataOrigin(BUCKET_BASE)).toBe('https://storage.googleapis.com');
  });

  it('names the local fixture origin, port included', () => {
    expect(dataOrigin('/genomeOS/data/atlas/')).toBeNull();
    expect(dataOrigin(LOCAL_BASE)).toBe('http://127.0.0.1:4323');
    expect(dataOrigin('http://localhost:4323/')).toBe('http://localhost:4323');
  });

  it.each([...HOSTILE_BASES, 'data/atlas/', BUCKET_BASE.slice(0, -1)])(
    'refuses the base %j',
    (base) => {
      expect(() => dataOrigin(base)).toThrow(/Atlas data base/);
    },
  );
});
