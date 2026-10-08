/**
 * Build-time catalog loading for the `/app/` page (fast-load design §B.6.1). Node-only: imported by
 * `app.astro` frontmatter, never by client code. A catalog that fails the strict browser schema fails
 * the build.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';

import { z } from 'zod';

import { atlasCatalogSchema, type AtlasCatalog } from '../atlas/contracts';
import { escapeInlineJson } from '../atlas/inline-catalog';

export const DEFAULT_ATLAS_CATALOG_PATH = 'public/data/atlas/catalog.json';

export function loadPageCatalog(
  catalogPath: string | undefined = DEFAULT_ATLAS_CATALOG_PATH,
  cwd: string = process.cwd(),
): { catalog: AtlasCatalog; json: string } {
  const resolved = path.resolve(cwd, catalogPath || DEFAULT_ATLAS_CATALOG_PATH);
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(resolved, 'utf8'));
  } catch (error) {
    throw new Error(
      `Atlas catalog ${resolved} could not be read as JSON: ${(error as Error).message}`,
    );
  }
  const parsed = atlasCatalogSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(
      `Atlas catalog ${resolved} fails atlasCatalogSchema:\n${z.prettifyError(parsed.error)}`,
    );
  }
  return { catalog: parsed.data, json: escapeInlineJson(JSON.stringify(raw)) };
}
