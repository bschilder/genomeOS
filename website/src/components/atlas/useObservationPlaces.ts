/** Lazy observation-place context loader for Atlas design §11. */

import { useEffect, useRef, useState } from 'react';

import {
  populatedPlaceCatalogSchema,
  type PopulatedPlaceCatalog,
} from '../../atlas/place-context';

export function useObservationPlaces(
  dataBaseUrl: string,
  enabled: boolean,
): PopulatedPlaceCatalog | null {
  const request = useRef<Promise<PopulatedPlaceCatalog> | null>(null);
  const [catalog, setCatalog] = useState<PopulatedPlaceCatalog | null>(null);

  useEffect(() => {
    if (!enabled || catalog) return;
    let active = true;
    const pending =
      request.current ??
      fetch(`${dataBaseUrl}ne-50m-populated-places.json`)
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
  }, [catalog, dataBaseUrl, enabled]);

  return catalog;
}
