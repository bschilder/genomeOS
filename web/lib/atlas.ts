/** Typed P4 client and viewport-resolution policy for P5 (design §10–§11). */

export type Support = "observed" | "interpolated" | "prior_dominated" | "unknown";

export interface Variant {
  variant_id: string;
  label: string;
  measurement: string;
  assumptions: string[];
  resolutions: number[];
  has_observations: boolean;
  has_surface: boolean;
  has_burden: boolean;
}

export interface SurfaceCell {
  h3_index: string;
  boundary: [number, number][] | null;
  lat: number;
  lon: number;
  post_mean: number;
  post_sd: number;
  q025: number;
  q975: number;
  support: Support;
}

export interface Observation {
  population_id: string;
  lat: number;
  lon: number;
  radius_km: number;
  ac: number;
  an: number;
  sampling_design: string;
  source: string;
}

export interface ArtifactResponse<T> {
  data_version: string;
  model_version: string;
  count: number;
  items: T[];
}

export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

const GLOBAL_SEGMENTS: Bounds[] = [-180, -90, 0, 90].flatMap((west) => [
  {west, south: -85, east: west + 90, north: 0},
  {west, south: 0, east: west + 90, north: 85},
]);

export function resolutionForZoom(resolutions: number[], zoom: number): number {
  if (!resolutions.length) throw new Error("surface has no published resolution");
  const sorted = [...resolutions].sort((a, b) => a - b);
  const requestedIndex = Math.max(0, Math.floor((zoom - 1) / 2));
  return sorted[Math.min(requestedIndex, sorted.length - 1)];
}

export function viewportSegments(bounds: Bounds, zoom: number): Bounds[] {
  if (zoom <= 2 || bounds.east - bounds.west >= 350) return GLOBAL_SEGMENTS;
  const south = Math.max(-85, bounds.south);
  const north = Math.min(85, bounds.north);
  const west = wrapLongitude(bounds.west);
  const east = wrapLongitude(bounds.east);
  return west <= east
    ? [{west, south, east, north}]
    : [
        {west, south, east: 180, north},
        {west: -180, south, east, north},
      ];
}

export async function fetchVariants(signal?: AbortSignal): Promise<ArtifactResponse<Variant>> {
  return getJson("/v1/atlas/variants", signal);
}

export async function fetchSurface(
  variantId: string,
  resolution: number,
  segments: Bounds[],
  signal?: AbortSignal,
): Promise<ArtifactResponse<SurfaceCell>> {
  const pages = await Promise.all(
    segments.map((bounds) => fetchSurfaceSegment(variantId, resolution, bounds, signal)),
  );
  const cells = new Map<string, SurfaceCell>();
  pages.flatMap((page) => page.items).forEach((cell) => {
    if (cell.boundary) cells.set(cell.h3_index, cell);
  });
  const first = pages[0];
  return {...first, count: cells.size, items: [...cells.values()]};
}

export function fetchObservations(
  variantId: string,
  signal?: AbortSignal,
): Promise<ArtifactResponse<Observation>> {
  return getJson(`/v1/atlas/observations?variant_id=${encodeURIComponent(variantId)}&limit=5000`, signal);
}

async function fetchSurfaceSegment(
  variantId: string,
  resolution: number,
  bounds: Bounds,
  signal?: AbortSignal,
): Promise<ArtifactResponse<SurfaceCell>> {
  const query = new URLSearchParams({
    variant_id: variantId,
    resolution: String(resolution),
    limit: "5000",
    west: String(bounds.west),
    south: String(bounds.south),
    east: String(bounds.east),
    north: String(bounds.north),
  });
  return getJson(`/v1/atlas/surface?${query}`, signal);
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {signal});
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

function wrapLongitude(value: number): number {
  return ((((value + 180) % 360) + 360) % 360) - 180;
}
