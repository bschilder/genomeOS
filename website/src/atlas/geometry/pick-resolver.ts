/** Geometry-aware surface pick resolution (fast-load spec 2026-10-07 §B.6.6).
 *
 * Surface chunks carry one pick id per chunk, so the cell under the cursor is
 * recovered from the picked position: the ellipsoid hit at elevation factor
 * 0; otherwise, on the globe, the picked Cartesian projected back along the
 * geocentric radial, which undoes the shader's `elevationNormal` displacement
 * exactly. For `extruded`, the cell is the first of the ≤ 7 candidate prisms (the
 * projected cell and its ring) that the pick ray enters, so depth-buffer
 * noise in the picked position only chooses the neighbourhood; without a ray,
 * or when it enters none of them, the hit altitude decides between the
 * projected cell and the taller neighbour whose wall was hit. In Columbus view
 * and 2D the same displacement shears the surface in the map frame instead,
 * and `map-frame-pick.ts` resolves the hit there (`input.mapFrame`).
 * Cesium-free.
 */

import {
  cellToLatLng,
  cellToVertexes,
  gridDisk,
  latLngToCell,
  vertexToLatLng,
} from 'h3-js';

import { rowForH3, type SurfaceArtifact } from '../surface-columns';
import type { SurfaceGeometry } from '../url-state';
import { MAX_HEIGHT_METRES } from '../visual-encoding';
import {
  alignToRay,
  firstDrawnRow,
  unshearedBase,
  type MapFrameHit,
} from './map-frame-pick';
import { CPU_EXTRUSION_EPSILON_METRES } from './surface-buffers';
import {
  geodeticToEcef,
  magnitude,
  scaleToGeocentricSurface,
  surfacePointToDegrees,
  type Vec3,
} from './wgs84';

/** Top-face slack: the 1 m CPU extrusion, 0.5 m, and 0.2% of the column for
 * depth-buffer noise in `scene.pickPosition`. */
function topTolerance(top: number): number {
  return CPU_EXTRUSION_EPSILON_METRES + 0.5 + 0.002 * top;
}

/** The pointer's pick ray: ECEF metres on the globe, the map frame's
 * `[x, y, height]` in `MapFrameHit`; `direction` need not be unit length. */
export interface PickRay {
  origin: Vec3;
  direction: Vec3;
}

export interface SurfacePickInput {
  cartesian: [number, number, number] | null;
  ellipsoidHit: { lat: number; lon: number } | null;
  factor: number;
  geometry: SurfaceGeometry;
  clearance: number;
  /** Only `extruded` reads it; null (or absent) keeps the altitude test. */
  ray?: PickRay | null;
  /** Columbus view and 2D: the hit and ray in the map frame. When set,
   * `cartesian` and `ray` are not read. */
  mapFrame?: MapFrameHit | null;
}

const dot = (a: Vec3, b: Vec3): number =>
  a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const minus = (a: Vec3, b: Vec3): Vec3 => [
  a[0] - b[0],
  a[1] - b[1],
  a[2] - b[2],
];
const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

/** `point` raised `lift` metres along its geocentric radial, as the mesh raises tops. */
function raised(point: Vec3, lift: number): Vec3 {
  const scale = 1 + lift / magnitude(point);
  return [point[0] * scale, point[1] * scale, point[2] * scale];
}

function groundPoint(lat: number, lon: number, clearance: number): Vec3 {
  const point: Vec3 = [0, 0, 0];
  geodeticToEcef(lon, lat, clearance, point);
  return point;
}

/**
 * Where `ray` enters the extruded prism of `cell` (`null` if it misses): the
 * mesh's corners and centre at the clearance, raised `lift` metres (surface-
 * buffers `buildFlatChunk`). Its walls lie in planes through the Earth's
 * centre and its top is a fan, so the prism is convex and the entry is the
 * latest crossing into any face's half-space (Cyrus-Beck). Below the
 * clearance the solid runs on to the centre; a ray reaches that part only
 * after the globe or another cell's top.
 */
function prismEntry(
  ray: PickRay,
  cell: string,
  clearance: number,
  lift: number,
): number | null {
  const ground = cellToVertexes(cell).map((vertex) => {
    const [lat, lon] = vertexToLatLng(vertex);
    return groundPoint(lat, lon, clearance);
  });
  const apex = raised(groundPoint(...cellToLatLng(cell), clearance), lift);
  const tops = ground.map((point) => raised(point, lift));
  let enter = Number.NEGATIVE_INFINITY;
  let exit = Number.POSITIVE_INFINITY;
  /** Keeps the part of the ray where `dot(normal, X) <= offset`; false when none. */
  const clip = (normal: Vec3, offset: number): boolean => {
    const along = dot(normal, ray.direction);
    const room = offset - dot(normal, ray.origin);
    if (along === 0) return room >= 0;
    if (along < 0) enter = Math.max(enter, room / along);
    else exit = Math.min(exit, room / along);
    return true;
  };
  for (let corner = 0; corner < ground.length; corner += 1) {
    const next = (corner + 1) % ground.length;
    const wall = cross(ground[corner], ground[next]);
    const roof = cross(minus(tops[corner], apex), minus(tops[next], apex));
    const wallSign = dot(wall, apex) > 0 ? -1 : 1;
    const roofSign = dot(roof, apex) < 0 ? -1 : 1;
    const inward = wall.map((axis) => axis * wallSign) as Vec3;
    const outward = roof.map((axis) => axis * roofSign) as Vec3;
    if (!clip(inward, 0) || !clip(outward, dot(outward, apex))) return null;
  }
  return enter <= exit && exit >= 0 ? Math.max(enter, 0) : null;
}

/** The candidate row whose prism `ray` enters first (ties to the lower row), or `null`. */
function firstPrismAlongRay(
  ray: PickRay,
  cell: string,
  surface: SurfaceArtifact,
  clearance: number,
  top: (row: number) => number,
): number | null {
  let best: number | null = null;
  let bestEntry = Number.POSITIVE_INFINITY;
  for (const candidate of gridDisk(cell, 1)) {
    const row = rowForH3(surface, candidate);
    if (row === null) continue;
    const entry = prismEntry(
      ray,
      candidate,
      clearance,
      CPU_EXTRUSION_EPSILON_METRES + top(row),
    );
    if (
      entry !== null &&
      (entry < bestEntry ||
        (entry === bestEntry && best !== null && row < best))
    ) {
      best = row;
      bestEntry = entry;
    }
  }
  return best;
}

/**
 * The altitude test: `row` while `altitude` is within its top (plus slack);
 * otherwise the hit is a wall, and the nearest `gridDisk(cell, 1)` neighbour
 * (by centre, ties to the lower row) whose top reaches the altitude wins; with
 * none, `row` stands (`null` off the grid).
 */
function altitudeRow(
  cell: string,
  row: number | null,
  { lat, lon }: { lat: number; lon: number },
  altitude: number,
  surface: SurfaceArtifact,
  top: (row: number) => number,
): number | null {
  if (row !== null && altitude <= top(row) + topTolerance(top(row))) return row;

  const hit = [0, 0, 0];
  geodeticToEcef(lon, lat, 0, hit);
  let best: number | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const neighbour of gridDisk(cell, 1)) {
    if (neighbour === cell) continue;
    const candidate = rowForH3(surface, neighbour);
    if (candidate === null) continue;
    if (altitude > top(candidate) + topTolerance(top(candidate))) continue;
    const [centreLat, centreLon] = cellToLatLng(neighbour);
    const centre = [0, 0, 0];
    geodeticToEcef(centreLon, centreLat, 0, centre);
    const distance = Math.hypot(
      centre[0] - hit[0],
      centre[1] - hit[1],
      centre[2] - hit[2],
    );
    if (
      best === null ||
      distance < bestDistance ||
      (distance === bestDistance && candidate < best)
    ) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best ?? row;
}

/**
 * Columbus view and 2D: the first drawn cell the ray meets near the hit
 * (`firstDrawnRow`). Without a ray, or when it meets none, the base recovered
 * from the hit's height (`unshearedBase`) gives the row, with the altitude
 * test for `extruded`.
 */
function mapFrameRow(
  input: SurfacePickInput,
  hit: MapFrameHit,
  surface: SurfaceArtifact,
  top: (row: number) => number,
  meshed: (row: number) => boolean,
): number | null {
  const maxLift = MAX_HEIGHT_METRES * input.factor;
  const point = hit.ray ? alignToRay(hit.point, hit.ray) : hit.point;
  if (hit.ray) {
    const first = firstDrawnRow(hit.ray, point, {
      clearance: input.clearance,
      geometry: input.geometry,
      maxLift,
      meshed,
      surface,
      top,
    });
    if (first !== null) return first;
  }
  const base = unshearedBase(point, input.clearance, maxLift);
  const cell = latLngToCell(base.lat, base.lon, surface.grid.resolution);
  const row = rowForH3(surface, cell);
  if (input.geometry !== 'extruded') return row;
  return altitudeRow(cell, row, base, base.lift, surface, top);
}

/**
 * The grid row under a surface or support pick, or `null` off the grid.
 * `heights(row)` is the row's render height at exaggeration 1 (`heightFor`
 * over the render tier; 0 for masked rows); on the globe only `extruded`
 * reads it. `meshed(row)` is true for rows the surface mesh draws (observed or
 * interpolated); only the map frame reads it, and without it a row counts as
 * meshed when its height is above 0.
 *
 * `input.mapFrame` (Columbus view and 2D): see `mapFrameRow`.
 *
 * `extruded` on the globe: with `input.ray`, the row of the first
 * `gridDisk(cell, 1)` prism the ray enters wins (ties to the lower row).
 * Without a ray, or when it enters none, the altitude test decides
 * (`altitudeRow`).
 */
export function resolveSurfaceRow(
  input: SurfacePickInput,
  surface: SurfaceArtifact,
  heights: (row: number) => number,
  meshed: (row: number) => boolean = (row) => heights(row) > 0,
): number | null {
  const resolution = surface.grid.resolution;
  if (input.factor <= 0) {
    if (!input.ellipsoidHit) return null;
    return rowForH3(
      surface,
      latLngToCell(input.ellipsoidHit.lat, input.ellipsoidHit.lon, resolution),
    );
  }
  const top = (candidate: number): number =>
    Math.max(0, heights(candidate)) * input.factor;
  if (input.mapFrame)
    return mapFrameRow(input, input.mapFrame, surface, top, meshed);
  if (!input.cartesian) return null;
  const onSurface = scaleToGeocentricSurface(input.cartesian);
  const { lat, lon } = surfacePointToDegrees(onSurface);
  const cell = latLngToCell(lat, lon, resolution);
  const row = rowForH3(surface, cell);
  if (input.geometry !== 'extruded') return row;

  if (input.ray) {
    const first = firstPrismAlongRay(
      input.ray,
      cell,
      surface,
      input.clearance,
      top,
    );
    if (first !== null) return first;
  }
  const altitude =
    magnitude(input.cartesian) - magnitude(onSurface) - input.clearance;
  return altitudeRow(cell, row, { lat, lon }, altitude, surface, top);
}
