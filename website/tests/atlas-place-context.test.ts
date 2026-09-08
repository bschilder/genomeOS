import { describe, expect, it } from 'vitest';

import type { Observation } from '../src/atlas/contracts';
import {
  nearestPlaceContext,
  populatedPlaceCatalogSchema,
} from '../src/atlas/place-context';

const observation = {
  lat: -33.867,
  lon: 151.208,
  population_label: 'Australia',
  radius_km: 9.3,
} as Observation;

const catalog = populatedPlaceCatalogSchema.parse({
  places: [
    {
      country: 'Australia',
      lat: -33.871373,
      lon: 151.212548,
      name: 'Sydney',
      region: 'New South Wales',
    },
    {
      country: 'Canada',
      lat: 46.066114,
      lon: -60.179981,
      name: 'Sydney',
      region: 'Nova Scotia',
    },
  ],
  revision: 'Natural Earth 5.1.2',
  source_url:
    'https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-populated-places/',
});

describe('observation place context', () => {
  it('adds the nearest same-country city and region for a precise observation', () => {
    expect(nearestPlaceContext(observation, catalog)).toEqual({
      distanceKm: expect.closeTo(0.63, 1),
      name: 'Sydney',
      region: 'New South Wales',
      revision: 'Natural Earth 5.1.2',
    });
  });

  it('does not imply city precision for a broad observation footprint', () => {
    expect(
      nearestPlaceContext({ ...observation, radius_km: 250 }, catalog),
    ).toBeNull();
  });

  it('does not cross a source-reported country boundary', () => {
    expect(
      nearestPlaceContext(
        { ...observation, population_label: 'Canada' },
        catalog,
      ),
    ).toBeNull();
  });
});
