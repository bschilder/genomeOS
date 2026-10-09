/**
 * Explorer data-provider wiring for Atlas design §11 and fast-load design §B.4, §B.6.1, §B.6.12:
 * the provider reads the inline catalog and shares the page's data worker, and the catalog's
 * Natural Earth context sources resolve by id against the site data base.
 */

import { useMemo } from 'react';

import { atlasRequestStallMs, atlasWorker } from '../../atlas/boot';
import {
  NATURAL_EARTH_BORDERS,
  NATURAL_EARTH_PLACES,
} from '../../atlas/context-sources';
import type { AtlasCatalog } from '../../atlas/contracts';
import { readInlineCatalog } from '../../atlas/inline-catalog';
import { StaticAtlasDataProvider } from '../../atlas/static-provider';

export interface ContextSourceUrls {
  borders: string;
  places: string;
}

/**
 * The page's data provider. Client only: the inline catalog and the data worker do not exist
 * during server rendering, so it is null there.
 */
export function useAtlasDataProvider(
  artifactDataBase: string,
  siteDataBase: string,
): StaticAtlasDataProvider | null {
  return useMemo(
    () =>
      typeof document === 'undefined'
        ? null
        : new StaticAtlasDataProvider({
            artifactDataBase,
            inlineCatalog: readInlineCatalog(document),
            requestStallMs: atlasRequestStallMs(),
            siteDataBase,
            worker: atlasWorker(),
          }),
    [artifactDataBase, siteDataBase],
  );
}

/** Absolute borders and places URLs once the catalog has loaded; null before. */
export function useContextSourceUrls(
  provider: StaticAtlasDataProvider | null,
  catalog: AtlasCatalog | null,
): ContextSourceUrls | null {
  return useMemo(
    () =>
      provider && catalog
        ? {
            borders: provider.contextSourceUrl(catalog, NATURAL_EARTH_BORDERS),
            places: provider.contextSourceUrl(catalog, NATURAL_EARTH_PLACES),
          }
        : null,
    [catalog, provider],
  );
}
