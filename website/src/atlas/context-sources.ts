/** Catalog-declared context layers, resolved by id instead of hard-coded file names (Atlas design §11; fast-load design §B.4). */

import type { AtlasCatalog } from './contracts';

export const NATURAL_EARTH_BORDERS = 'natural-earth-admin-0';
export const NATURAL_EARTH_PLACES = 'natural-earth-populated-places';

export function contextSourceKey(catalog: AtlasCatalog, id: string): string {
  const source = catalog.context_sources.find(
    (candidate) => candidate.id === id,
  );
  if (!source)
    throw new Error(`The Atlas catalog declares no context source "${id}"`);
  return source.url;
}
