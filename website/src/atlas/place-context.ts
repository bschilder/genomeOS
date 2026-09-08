/** Conservative geographic context for measured observations (Atlas design §11). */

import { z } from 'zod';

import type { Observation } from './contracts';

const populatedPlaceSchema = z.strictObject({
  country: z.string().trim().min(1),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180),
  name: z.string().trim().min(1),
  region: z.string().trim().min(1).optional(),
});

export const populatedPlaceCatalogSchema = z.strictObject({
  places: z.array(populatedPlaceSchema),
  revision: z.string().trim().min(1),
  source_url: z.url(),
});

export type PopulatedPlaceCatalog = z.infer<typeof populatedPlaceCatalogSchema>;

export interface ObservationPlaceContext {
  distanceKm: number;
  name: string;
  region?: string;
  revision: string;
}

const EARTH_RADIUS_KM = 6_371.0088;
const MAX_OBSERVATION_RADIUS_KM = 25;
const MAX_PLACE_DISTANCE_KM = 30;

function radians(value: number): number {
  return (value * Math.PI) / 180;
}

function distanceKm(
  first: { lat: number; lon: number },
  second: { lat: number; lon: number },
): number {
  const latitudeDelta = radians(second.lat - first.lat);
  const longitudeDelta = radians(second.lon - first.lon);
  const firstLatitude = radians(first.lat);
  const secondLatitude = radians(second.lat);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(firstLatitude) *
      Math.cos(secondLatitude) *
      Math.sin(longitudeDelta / 2) ** 2;
  return (
    2 *
    EARTH_RADIUS_KM *
    Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))
  );
}

function normalizedCountry(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/gi, '')
    .toLowerCase();
}

export function nearestPlaceContext(
  observation: Pick<
    Observation,
    'lat' | 'lon' | 'population_label' | 'radius_km'
  >,
  catalog: PopulatedPlaceCatalog,
): ObservationPlaceContext | null {
  if (observation.radius_km > MAX_OBSERVATION_RADIUS_KM) return null;
  const sourceCountry = normalizedCountry(observation.population_label);
  let nearest: PopulatedPlaceCatalog['places'][number] | null = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const place of catalog.places) {
    if (normalizedCountry(place.country) !== sourceCountry) continue;
    const candidateDistance = distanceKm(observation, place);
    if (candidateDistance < nearestDistance) {
      nearest = place;
      nearestDistance = candidateDistance;
    }
  }
  if (!nearest || nearestDistance > MAX_PLACE_DISTANCE_KM) return null;
  return {
    distanceKm: nearestDistance,
    name: nearest.name,
    ...(nearest.region ? { region: nearest.region } : {}),
    revision: catalog.revision,
  };
}
