/**
 * Browser-test fixture for the Atlas explorer (fast-load design §B.8).
 *
 * `npm run build:e2e` inlines the committed compact catalog
 * (`tests/fixtures/atlas/e2e/catalog.json`) into `/app/`. This fixture fulfils
 * exactly that catalog's fetched object keys (grid, render, detail,
 * observations) from the committed e2e tree. It never re-encodes, never
 * `route.fetch()`es production files and never touches the inline catalog.
 *
 * It imports no app modules: `scripts/capture-*.mjs` load it under plain Node
 * type stripping, which cannot resolve the app's extensionless imports.
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import type { Page, Route } from '@playwright/test';

export type ArtifactTier = 'grid' | 'render' | 'detail' | 'observations';

/** The catalog fields browser tests read (a structural subset of `atlasCatalogSchema`). */
export interface FixtureCatalog {
  grids: Record<string, { url: string }>;
  artifacts: {
    id: string;
    model_version: string;
    data_version: string;
    surface_url: string;
    observations_url: string | null;
    downloads: {
      manifest: { url: string };
      observations: { url: string } | null;
      surface: { url: string };
    };
    web: {
      grid_sha256: string;
      render: { url: string };
      detail: { url: string };
    };
  }[];
}

export interface AtlasBrowserFixtureOptions {
  /** The served `/app/` page; relative to the test `baseURL` unless absolute. */
  appUrl?: string;
}

export interface TierDelay {
  hits(): number;
  release(): void;
}

export interface TierOverride {
  hits(): number;
  restore(): Promise<void>;
}

/** Committed compact export (fast-load design §B.5 "E2E fixture tree"). */
export const E2E_FIXTURE_DIR = path.resolve(
  import.meta.dirname,
  'fixtures',
  'atlas',
  'e2e',
);
export const E2E_CATALOG_PATH = path.join(E2E_FIXTURE_DIR, 'catalog.json');
/** `artifactDataBase` of an e2e build (BASE_PATH `/`; same-origin data in Part B). */
export const E2E_ARTIFACT_DATA_BASE = '/data/atlas/';

const DEFAULT_APP_URL = '/app/';
const INLINE_CATALOG =
  /<script\b[^>]*\bid="atlas-catalog"[^>]*>([\s\S]*?)<\/script>/;
const inlineCatalogs = new Map<string, Promise<FixtureCatalog>>();
let e2eObjects: Map<string, Buffer> | null = null;

export function extractInlineCatalog(html: string): FixtureCatalog {
  const match = INLINE_CATALOG.exec(html);
  if (match === null)
    throw new Error(
      'The /app/ page has no inline <script id="atlas-catalog"> element.',
    );
  return JSON.parse(match[1]) as FixtureCatalog;
}

export function artifactTierKey(
  catalog: FixtureCatalog,
  id: string,
  tier: ArtifactTier,
): string {
  const matches = catalog.artifacts.filter((artifact) => artifact.id === id);
  if (matches.length !== 1)
    throw new Error(
      `Expected exactly one catalog artifact "${id}", found ${matches.length}.`,
    );
  const artifact = matches[0];
  if (tier === 'grid') {
    const grid = catalog.grids[artifact.web.grid_sha256];
    if (grid === undefined)
      throw new Error(
        `The catalog has no grid ${artifact.web.grid_sha256} for "${id}".`,
      );
    return grid.url;
  }
  if (tier === 'render') return artifact.web.render.url;
  if (tier === 'detail') return artifact.web.detail.url;
  if (artifact.observations_url === null)
    throw new Error(`"${id}" has no observations.`);
  return artifact.observations_url;
}

/** Every key the client fetches for some artifact, sorted. */
export function fetchedKeys(catalog: FixtureCatalog): string[] {
  const keys = new Set<string>();
  for (const grid of Object.values(catalog.grids)) keys.add(grid.url);
  for (const artifact of catalog.artifacts) {
    keys.add(artifact.web.render.url);
    keys.add(artifact.web.detail.url);
    if (artifact.observations_url !== null) keys.add(artifact.observations_url);
  }
  return [...keys].sort();
}

/** Keys are unique relative paths, so a suffix match works for any data base. */
export function urlMatchesKey(url: URL, key: string): boolean {
  return url.pathname.endsWith(`/${key}`);
}

export function readE2eCatalog(): FixtureCatalog {
  return JSON.parse(readFileSync(E2E_CATALOG_PATH, 'utf8')) as FixtureCatalog;
}

export function readE2eObject(key: string): Buffer {
  const file = path.join(E2E_FIXTURE_DIR, key);
  if (!existsSync(file))
    throw new Error(
      `The e2e fixture tree has no object for catalog key "${key}" (${file}).`,
    );
  return readFileSync(file);
}

/** The catalog the served `/app/` page inlines (cached per `appUrl`). */
export function readInlineCatalog(
  page: Page,
  appUrl: string = DEFAULT_APP_URL,
): Promise<FixtureCatalog> {
  const cached = inlineCatalogs.get(appUrl);
  if (cached !== undefined) return cached;
  const loading = (async () => {
    const response = await page.request.get(appUrl);
    if (!response.ok())
      throw new Error(`GET ${appUrl} returned HTTP ${response.status()}.`);
    return extractInlineCatalog(await response.text());
  })();
  inlineCatalogs.set(appUrl, loading);
  loading.catch(() => inlineCatalogs.delete(appUrl));
  return loading;
}

function contentTypeFor(key: string): string {
  return key.endsWith('.json')
    ? 'application/json'
    : 'application/octet-stream';
}

function e2eObjectMap(): Map<string, Buffer> {
  e2eObjects ??= new Map(
    fetchedKeys(readE2eCatalog()).map(
      (key) => [key, readE2eObject(key)] as const,
    ),
  );
  return e2eObjects;
}

function gridIds(catalog: FixtureCatalog): string {
  return JSON.stringify(Object.keys(catalog.grids).sort());
}

/**
 * Serve the committed e2e objects for the e2e build's inline catalog and keep
 * map tiles offline. Fails loudly when `dist/` is not an e2e build.
 */
export async function installAtlasBrowserFixture(
  page: Page,
  options: AtlasBrowserFixtureOptions = {},
): Promise<void> {
  const served = await readInlineCatalog(page, options.appUrl);
  if (gridIds(served) !== gridIds(readE2eCatalog()))
    throw new Error(
      'The served /app/ page does not inline tests/fixtures/atlas/e2e/catalog.json. Build it with `npm run build:e2e` before running browser tests.',
    );
  const objects = e2eObjectMap();
  const keyFor = (url: URL): string | undefined =>
    [...objects.keys()].find((key) => urlMatchesKey(url, key));
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.abort(),
  );
  await page.route(
    (url) => keyFor(url) !== undefined,
    async (route) => {
      const key = keyFor(new URL(route.request().url()));
      if (key === undefined) return route.fallback();
      await route.fulfill({
        body: objects.get(key),
        contentType: contentTypeFor(key),
        status: 200,
      });
    },
  );
}

/**
 * Hold one artifact tier for `ms` (or until `release()` when `ms` is
 * `Number.POSITIVE_INFINITY`), then hand it to the next route handler.
 */
export async function delayArtifactTier(
  page: Page,
  id: string,
  tier: ArtifactTier,
  ms: number,
  options: AtlasBrowserFixtureOptions = {},
): Promise<TierDelay> {
  const key = artifactTierKey(
    await readInlineCatalog(page, options.appUrl),
    id,
    tier,
  );
  let hits = 0;
  let released = false;
  const waiting = new Set<() => void>();
  await page.route(
    (url) => urlMatchesKey(url, key),
    async (route) => {
      hits += 1;
      if (!released) {
        await new Promise<void>((resolve) => {
          const finish = (): void => {
            clearTimeout(timer);
            waiting.delete(finish);
            resolve();
          };
          const timer = Number.isFinite(ms)
            ? setTimeout(finish, ms)
            : undefined;
          waiting.add(finish);
        });
      }
      await route.fallback();
    },
  );
  return {
    hits: () => hits,
    release: () => {
      released = true;
      for (const finish of [...waiting]) finish();
    },
  };
}

async function overrideArtifactTier(
  page: Page,
  id: string,
  tier: ArtifactTier,
  options: AtlasBrowserFixtureOptions,
  respond: (route: Route, key: string) => Promise<void>,
): Promise<TierOverride> {
  const key = artifactTierKey(
    await readInlineCatalog(page, options.appUrl),
    id,
    tier,
  );
  let hits = 0;
  const matcher = (url: URL): boolean => urlMatchesKey(url, key);
  const handler = async (route: Route): Promise<void> => {
    hits += 1;
    await respond(route, key);
  };
  await page.route(matcher, handler);
  return { hits: () => hits, restore: () => page.unroute(matcher, handler) };
}

/** Serve the e2e object with its last byte flipped (a checksum failure). */
export function corruptArtifactTier(
  page: Page,
  id: string,
  tier: ArtifactTier,
  options: AtlasBrowserFixtureOptions = {},
): Promise<TierOverride> {
  return overrideArtifactTier(page, id, tier, options, async (route, key) => {
    const body = Buffer.from(readE2eObject(key));
    body[body.length - 1] ^= 0xff;
    await route.fulfill({
      body,
      contentType: contentTypeFor(key),
      status: 200,
    });
  });
}

/** Fail every request for one artifact tier at the network layer. */
export function failArtifactTier(
  page: Page,
  id: string,
  tier: ArtifactTier,
  options: AtlasBrowserFixtureOptions = {},
): Promise<TierOverride> {
  return overrideArtifactTier(page, id, tier, options, (route) =>
    route.abort('failed'),
  );
}

/** Distinct artifact ids in `data-atlas-displayed`, sorted. */
export async function displayedArtifactIds(page: Page): Promise<string[]> {
  const value = await page
    .locator('.atlas-explorer')
    .getAttribute('data-atlas-displayed');
  return [...new Set((value ?? '').split(/\s+/).filter(Boolean))].sort();
}
