/** Performance specs measure the repository's full data, never the e2e catalog or a stale build (fast-load design §B.1). */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { isDeepStrictEqual } from 'node:util';

import {
  extractInlineCatalog,
  type FixtureCatalog,
} from '../atlas-browser-fixture';

const PRODUCTION_CATALOG = path.resolve(
  import.meta.dirname,
  '../../public/data/atlas/catalog.json',
);

/**
 * The catalog with the keys of its canonical JSON files (`surface_url`, `observations_url`,
 * `downloads.*.url`) blanked. Part C's `encode_atlas_web.py --with-downloads` rewrites exactly
 * those to bucket keys and keeps every sha256 beside them (design §C.2), so a staged catalog still
 * has the repository catalog's content.
 */
function withoutDownloadKeys(catalog: unknown): Record<string, unknown> {
  const copy = structuredClone(catalog) as Record<string, unknown>;
  if (!Array.isArray(copy.artifacts)) return copy;
  for (const artifact of copy.artifacts as Record<string, unknown>[]) {
    artifact.surface_url = null;
    artifact.observations_url = null;
    const downloads = (artifact.downloads ?? {}) as Record<
      string,
      { url?: unknown } | null
    >;
    for (const entry of Object.values(downloads)) if (entry) entry.url = null;
  }
  return copy;
}

/**
 * Fail loudly unless `${baseUrl}/app/` inlines `public/data/atlas/catalog.json`: every field equal,
 * except that the canonical JSON files may sit at their Part C bucket keys (same sha256).
 */
export async function assertProductionBuild(
  baseUrl: string,
): Promise<FixtureCatalog> {
  const appUrl = new URL('/app/', baseUrl).href;
  const response = await fetch(appUrl);
  if (!response.ok)
    throw new Error(`GET ${appUrl} returned HTTP ${response.status}.`);
  const served = extractInlineCatalog(await response.text());
  const production: unknown = JSON.parse(
    readFileSync(PRODUCTION_CATALOG, 'utf8'),
  );
  const servedContent = withoutDownloadKeys(served);
  const productionContent = withoutDownloadKeys(production);
  const differing = [
    ...new Set([
      ...Object.keys(servedContent),
      ...Object.keys(productionContent),
    ]),
  ]
    .sort()
    .filter(
      (field) =>
        !isDeepStrictEqual(servedContent[field], productionContent[field]),
    );
  if (differing.length > 0)
    throw new Error(
      `${appUrl} does not inline public/data/atlas/catalog.json (${differing.join(', ')} differ). Performance specs measure full data: run \`npm run build\` without ATLAS_CATALOG_PATH.`,
    );
  return served;
}
