/** Lazy observation-place context loader for Atlas design §11. */

import { useEffect, useRef, useState } from 'react';

import {
  populatedPlaceCatalogSchema,
  type PopulatedPlaceCatalog,
} from '../../atlas/place-context';

/** `url` is the catalog's populated-places source resolved against the site data base, or null. */
export function useObservationPlaces(
  url: string | null,
  enabled: boolean,
): PopulatedPlaceCatalog | null {
  const request = useRef<Promise<PopulatedPlaceCatalog> | null>(null);
  const [catalog, setCatalog] = useState<PopulatedPlaceCatalog | null>(null);

  useEffect(() => {
    if (!enabled || catalog || !url) return;
    let active = true;
    const pending =
      request.current ??
      fetch(url)
        .then((response) => {
          if (!response.ok)
            throw new Error(
              `Place context request failed (${response.status}).`,
            );
          return response.json();
        })
        .then((value) => populatedPlaceCatalogSchema.parse(value));
    request.current = pending;
    void pending
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch((caught) => {
        request.current = null;
        console.warn(
          'Optional observation place context is unavailable.',
          caught,
        );
      });
    return () => {
      active = false;
    };
  }, [catalog, enabled, url]);

  return catalog;
}
