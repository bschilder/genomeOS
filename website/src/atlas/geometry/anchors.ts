/** Observation anchor heights from the render tier (fast-load spec 2026-10-07
 * §B.6.5 last bullet, §B.6.8 elevation rule).
 *
 * Reproduces the legacy `observationSurfaceAnchor` with Cesium-free math and
 * the worker's float32 vertex means, so anchors sit on the mesh the GPU draws.
 * Presentation only: observation coordinates and radii are never changed.
 */

import { latLngToCell } from 'h3-js';

import { heightFor } from '../visual-encoding';
import {
  isSmoothGeometry,
  vertexMeans,
  type MeshInput,
} from './surface-buffers';
import { isSupportedCode, supportName } from './support-codes';
import { gridRowOf } from './topology';
import { geodeticSurfaceNormal, geodeticToEcef } from './wgs84';

export interface ObservationAnchors {
  /** Anchor height at exaggeration 1, one per point. */
  heights: Float64Array;
  /** Per point: lat, lon, height of the three triangle vertices; NaN when the
   * anchor is flat (no triangle), matching the legacy `triangle: null`. */
  triangles: Float64Array;
}

interface MeshVertex {
  height: number;
  lat: number;
  lon: number;
}

type Plane2 = readonly [number, number];

function cross(a: readonly number[], b: readonly number[]): number[] {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalized(vector: readonly number[]): number[] {
  const magnitude = Math.sqrt(
    vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2],
  );
  return [vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude];
}

function tangentBasis(origin: readonly number[]): {
  east: number[];
  north: number[];
} {
  const up = geodeticSurfaceNormal(origin);
  let east = cross([0, 0, 1], up);
  if (east[0] * east[0] + east[1] * east[1] + east[2] * east[2] < 1e-12)
    east = cross([1, 0, 0], up);
  east = normalized(east);
  return { east, north: normalized(cross(up, east)) };
}

function projectToTangent(
  lat: number,
  lon: number,
  origin: readonly number[],
  east: readonly number[],
  north: readonly number[],
): Plane2 {
  const position = [0, 0, 0];
  geodeticToEcef(lon, lat, 0, position);
  const delta = [
    position[0] - origin[0],
    position[1] - origin[1],
    position[2] - origin[2],
  ];
  return [
    delta[0] * east[0] + delta[1] * east[1] + delta[2] * east[2],
    delta[0] * north[0] + delta[1] * north[1] + delta[2] * north[2],
  ];
}

function barycentricWeights(
  point: Plane2,
  first: Plane2,
  second: Plane2,
  third: Plane2,
): [number, number, number] {
  const denominator =
    (second[1] - third[1]) * (first[0] - third[0]) +
    (third[0] - second[0]) * (first[1] - third[1]);
  if (Math.abs(denominator) < 1e-9) return [-1, -1, -1];
  const a =
    ((second[1] - third[1]) * (point[0] - third[0]) +
      (third[0] - second[0]) * (point[1] - third[1])) /
    denominator;
  const b =
    ((third[1] - first[1]) * (point[0] - third[0]) +
      (first[0] - third[0]) * (point[1] - third[1])) /
    denominator;
  return [a, b, 1 - a - b];
}

function sampleTriangle(
  vertices: readonly MeshVertex[],
  lat: number,
  lon: number,
): { triangle: [MeshVertex, MeshVertex, MeshVertex]; weights: number[] } {
  const center = vertices[0];
  const origin = [0, 0, 0];
  geodeticToEcef(center.lon, center.lat, 0, origin);
  const { east, north } = tangentBasis(origin);
  const point = projectToTangent(lat, lon, origin, east, north);
  const projected = vertices.map((vertex) =>
    projectToTangent(vertex.lat, vertex.lon, origin, east, north),
  );
  const corners = vertices.length - 1;
  let closest: {
    triangle: [MeshVertex, MeshVertex, MeshVertex];
    weights: number[];
  } | null = null;
  let closestMinimum = Number.NEGATIVE_INFINITY;
  for (let corner = 0; corner < corners; corner += 1) {
    const indexes = [0, corner + 1, ((corner + 1) % corners) + 1];
    const weights = barycentricWeights(
      point,
      projected[indexes[0]],
      projected[indexes[1]],
      projected[indexes[2]],
    );
    const triangle = indexes.map((index) => vertices[index]) as [
      MeshVertex,
      MeshVertex,
      MeshVertex,
    ];
    const minimum = Math.min(...weights);
    if (minimum >= -1e-6) return { triangle, weights };
    if (minimum > closestMinimum) {
      closest = { triangle, weights };
      closestMinimum = minimum;
    }
  }
  if (!closest) throw new Error('surface mesh has no triangles');
  const clamped = closest.weights.map((weight) => Math.max(0, weight));
  const sum = clamped.reduce((total, weight) => total + weight, 0);
  if (sum === 0) throw new Error('surface mesh cannot anchor observation');
  return {
    triangle: closest.triangle,
    weights: clamped.map((weight) => weight / sum),
  };
}

/** Anchors for interleaved `[lon0, lat0, lon1, lat1, …]` observation points. */
export function observationAnchors(
  input: MeshInput,
  points: Float64Array,
): ObservationAnchors {
  const count = points.length / 2;
  const heights = new Float64Array(count);
  const triangles = new Float64Array(count * 9).fill(Number.NaN);
  const smooth = isSmoothGeometry(input.geometry);
  const vertexHeights = smooth
    ? (input.vertexHeights ?? vertexMeans(input).heights)
    : null;
  const { topology } = input;
  for (let index = 0; index < count; index += 1) {
    const lon = points[index * 2];
    const lat = points[index * 2 + 1];
    const row = gridRowOf(
      input.grid,
      latLngToCell(lat, lon, input.grid.resolution),
    );
    if (row === null) continue;
    const code = input.support[row];
    const flatHeight = heightFor(
      supportName(code),
      input.values[row],
      input.domain,
      1,
    );
    if (!vertexHeights || !isSupportedCode(code)) {
      heights[index] = flatHeight;
      continue;
    }
    const vertices: MeshVertex[] = [
      {
        height: flatHeight,
        lat: topology.centreLat[row],
        lon: topology.centreLon[row],
      },
    ];
    for (
      let corner = topology.cornerOffsets[row];
      corner < topology.cornerOffsets[row + 1];
      corner += 1
    ) {
      const id = topology.cornerIds[corner];
      vertices.push({
        height: vertexHeights[id],
        lat: topology.vertexLat[id],
        lon: topology.vertexLon[id],
      });
    }
    const sample = sampleTriangle(vertices, lat, lon);
    heights[index] = sample.weights.reduce(
      (height, weight, vertex) =>
        height + sample.triangle[vertex].height * weight,
      0,
    );
    sample.triangle.forEach((vertex, corner) =>
      triangles.set(
        [vertex.lat, vertex.lon, vertex.height],
        index * 9 + corner * 3,
      ),
    );
  }
  return { heights, triangles };
}
