/** Cesium-free H3 boundary parts for Atlas design §11 and fast-load spec
 * 2026-10-07 §B.6.5 (support, edges and highlight share one split).
 */

import { cellToBoundary, cellToLatLng, type H3IndexInput } from 'h3-js';

// Cesium cannot tessellate a polygon whose edges collectively enclose a pole
// (https://github.com/CesiumGS/cesium/issues/4801). Only those H3 cells are
// split into triangles, with a renderer-only seam kept just off the singularity.
const POLAR_SEAM_LONGITUDE = 179;
const POLE_EPSILON_DEGREES = 0.000001;

export function h3BoundaryDegrees(h3Index: H3IndexInput): [number, number][] {
  return cellToBoundary(h3Index).map(([lat, lon]) => [lon, lat]);
}

export function h3PolygonParts(h3Index: H3IndexInput): [number, number][][] {
  const boundary = h3BoundaryDegrees(h3Index);
  const longitudeSpan =
    Math.max(...boundary.map(([lon]) => lon)) -
    Math.min(...boundary.map(([lon]) => lon));
  const isPolar =
    longitudeSpan > 180 && boundary.some(([, lat]) => Math.abs(lat) > 89);
  if (!isPolar) return [boundary];

  const [centerLat, centerLon] = cellToLatLng(h3Index);
  const center: [number, number] = [centerLon, centerLat];
  const poleLatitude = Math.sign(centerLat) * (90 - POLE_EPSILON_DEGREES);
  const parts: [number, number][][] = [];
  for (let index = 0; index < boundary.length; index += 1) {
    const first = boundary[index];
    const second = boundary[(index + 1) % boundary.length];
    if (Math.abs(first[0] - second[0]) <= 180) {
      parts.push([center, first, second]);
      continue;
    }
    const firstSeam: [number, number] = [
      Math.sign(first[0]) * POLAR_SEAM_LONGITUDE,
      poleLatitude,
    ];
    const secondSeam: [number, number] = [
      Math.sign(second[0]) * POLAR_SEAM_LONGITUDE,
      poleLatitude,
    ];
    parts.push([center, first, firstSeam], [center, secondSeam, second]);
  }
  return parts;
}

/** True when the cell's own boundary spans more than 180° of longitude. */
export function crossesAntimeridian(h3Index: H3IndexInput): boolean {
  let min = Infinity;
  let max = -Infinity;
  for (const [, lon] of cellToBoundary(h3Index)) {
    if (lon < min) min = lon;
    if (lon > max) max = lon;
  }
  return max - min > 180;
}
