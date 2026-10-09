/** Performance specs measure full data, never the e2e catalog (fast-load design §B.1). */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import {
  extractInlineCatalog,
  type FixtureCatalog,
} from '../atlas-browser-fixture';

const PRODUCTION_CATALOG = path.resolve(
  import.meta.dirname,
  '../../public/data/atlas/catalog.json',
);

/** Fail loudly unless `${baseUrl}/app/` inlines `public/data/atlas/catalog.json`. */
export async function assertProductionBuild(
  baseUrl: string,
): Promise<FixtureCatalog> {
  const appUrl = new URL('/app/', baseUrl).href;
  const response = await fetch(appUrl);
  if (!response.ok)
    throw new Error(`GET ${appUrl} returned HTTP ${response.status}.`);
  const served = extractInlineCatalog(await response.text());
  const production = JSON.parse(
    readFileSync(PRODUCTION_CATALOG, 'utf8'),
  ) as FixtureCatalog;
  const grids = (catalog: FixtureCatalog): string =>
    JSON.stringify(Object.keys(catalog.grids).sort());
  if (grids(served) !== grids(production))
    throw new Error(
      `${appUrl} does not inline public/data/atlas/catalog.json. Performance specs measure full data: run \`npm run build\` without ATLAS_CATALOG_PATH.`,
    );
  return served;
}
