/** Geometry-aware surface pick resolution (fast-load spec 2026-10-07 §B.6.6).
 *
 * Surface chunks carry one pick id per chunk, so the cell under the cursor is
 * recovered from the picked position: the ellipsoid hit at elevation factor
 * 0; otherwise the picked Cartesian projected back along the geocentric
 * radial, which undoes the shader's `elevationNormal` displacement exactly.
 * For `extruded`, the hit altitude decides between the projected cell and the
 * taller neighbour whose wall was hit. Cesium-free.
 */

import { cellToLatLng, gridDisk, latLngToCell } from 'h3-js';

import { rowForH3, type SurfaceArtifact } from '../surface-columns';
import type { SurfaceGeometry } from '../url-state';
import { CPU_EXTRUSION_EPSILON_METRES } from './surface-buffers';
import {
  geodeticToEcef,
  magnitude,
  scaleToGeocentricSurface,
  surfacePointToDegrees,
} from './wgs84';

/** Top-face slack: the 1 m CPU extrusion, 0.5 m, and 0.2% of the column for
 * depth-buffer noise in `scene.pickPosition`. */
function topTolerance(top: number): number {
  return CPU_EXTRUSION_EPSILON_METRES + 0.5 + 0.002 * top;
}

export interface SurfacePickInput {
  cartesian: [number, number, number] | null;
  ellipsoidHit: { lat: number; lon: number } | null;
  factor: number;
  geometry: SurfaceGeometry;
  clearance: number;
}

/**
 * The grid row under a surface or support pick, or `null` off the grid.
 * `heights(row)` is the row's render height at exaggeration 1 (`heightFor`
 * over the render tier; 0 for masked rows); only `extruded` reads it.
 */
export function resolveSurfaceRow(
  input: SurfacePickInput,
  surface: SurfaceArtifact,
  heights: (row: number) => number,
): number | null {
  const resolution = surface.grid.resolution;
  if (input.factor <= 0) {
    if (!input.ellipsoidHit) return null;
    return rowForH3(
      surface,
      latLngToCell(input.ellipsoidHit.lat, input.ellipsoidHit.lon, resolution),
    );
  }
  if (!input.cartesian) return null;
  const onSurface = scaleToGeocentricSurface(input.cartesian);
  const { lat, lon } = surfacePointToDegrees(onSurface);
  const cell = latLngToCell(lat, lon, resolution);
  const row = rowForH3(surface, cell);
  if (input.geometry !== 'extruded') return row;

  const altitude =
    magnitude(input.cartesian) - magnitude(onSurface) - input.clearance;
  const top = (candidate: number): number =>
    Math.max(0, heights(candidate)) * input.factor;
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
      distance < bestDistance ||
      (distance === bestDistance && candidate < best!)
    ) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best ?? row;
}
