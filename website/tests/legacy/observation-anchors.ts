/** Main-thread observation anchors of the pre-2026-10-07 builder (parity reference only).
 *
 * Production takes anchors from the data worker (spec 2026-10-07 §B.6.5);
 * this copy stays for tests that compare against it.
 */

import { latLngToCell } from 'h3-js';
import { Cartesian3, Ellipsoid } from 'cesium';

import type {
  SurfaceArtifact as SurfaceArtifactJson,
  SurfaceCell,
} from '../../src/atlas/contracts';
import type { ObservationSurfaceAnchor } from '../../src/atlas/scene/observation-symbols';
import type { SurfaceGeometry } from '../../src/atlas/url-state';
import { heightForCell, type Metric } from '../../src/atlas/visual-encoding';
import {
  surfaceMeshForCell,
  surfaceVertexHeights,
  type SurfaceCellMesh,
  type SurfaceMeshVertex,
} from './surface-mesh';

export interface GeographicPoint {
  lat: number;
  lon: number;
}

export interface ObservationSurfaceContext {
  cells: ReadonlyMap<string, SurfaceCell>;
  vertexHeights: ReadonlyMap<string, number>;
}

interface TriangleSample {
  triangle: readonly [SurfaceMeshVertex, SurfaceMeshVertex, SurfaceMeshVertex];
  weights: readonly [number, number, number];
}

const SMOOTH_GEOMETRIES: ReadonlySet<SurfaceGeometry> = new Set([
  'triangles',
  'honmoon',
  'honmoon-fill',
]);

function tangentBasis(origin: Cartesian3): {
  east: Cartesian3;
  north: Cartesian3;
} {
  const up = Ellipsoid.WGS84.geodeticSurfaceNormal(origin, new Cartesian3());
  let east = Cartesian3.cross(Cartesian3.UNIT_Z, up, new Cartesian3());
  if (Cartesian3.magnitudeSquared(east) < 1e-12)
    east = Cartesian3.cross(Cartesian3.UNIT_X, up, east);
  Cartesian3.normalize(east, east);
  return {
    east,
    north: Cartesian3.normalize(
      Cartesian3.cross(up, east, new Cartesian3()),
      new Cartesian3(),
    ),
  };
}

function projectToTangent(
  point: GeographicPoint,
  origin: Cartesian3,
  east: Cartesian3,
  north: Cartesian3,
): readonly [number, number] {
  const position = Cartesian3.fromDegrees(point.lon, point.lat);
  const delta = Cartesian3.subtract(position, origin, new Cartesian3());
  return [Cartesian3.dot(delta, east), Cartesian3.dot(delta, north)];
}

function barycentricWeights(
  point: readonly [number, number],
  first: readonly [number, number],
  second: readonly [number, number],
  third: readonly [number, number],
): readonly [number, number, number] {
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

function triangleAtPoint(
  mesh: SurfaceCellMesh,
  point: GeographicPoint,
): TriangleSample {
  const center = mesh.vertices[0];
  const origin = Cartesian3.fromDegrees(center.lon, center.lat);
  const { east, north } = tangentBasis(origin);
  const projectedPoint = projectToTangent(point, origin, east, north);
  const projectedVertices = mesh.vertices.map((vertex) =>
    projectToTangent(vertex, origin, east, north),
  );
  let closest: TriangleSample | null = null;
  let closestMinimum = Number.NEGATIVE_INFINITY;
  for (let index = 0; index < mesh.indices.length; index += 3) {
    const indexes = mesh.indices.slice(index, index + 3) as [
      number,
      number,
      number,
    ];
    const weights = barycentricWeights(
      projectedPoint,
      projectedVertices[indexes[0]],
      projectedVertices[indexes[1]],
      projectedVertices[indexes[2]],
    );
    const triangle = indexes.map((vertex) => mesh.vertices[vertex]) as [
      SurfaceMeshVertex,
      SurfaceMeshVertex,
      SurfaceMeshVertex,
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
    weights: clamped.map((weight) => weight / sum) as [number, number, number],
  };
}

export function observationSurfaceContext(
  surface: SurfaceArtifactJson,
  metric: Metric,
  geometry: SurfaceGeometry = 'triangles',
): ObservationSurfaceContext {
  return {
    cells: new Map(surface.cells.map((cell) => [cell.h3_index, cell])),
    vertexHeights: SMOOTH_GEOMETRIES.has(geometry)
      ? surfaceVertexHeights(
          surface.cells,
          surface.artifact.metric_domains[metric],
          metric,
        )
      : new Map(),
  };
}

export function observationSurfaceAnchor(
  point: GeographicPoint,
  surface: SurfaceArtifactJson,
  metric: Metric,
  geometry: SurfaceGeometry,
  context = observationSurfaceContext(surface, metric, geometry),
): ObservationSurfaceAnchor {
  const cell = context.cells.get(
    latLngToCell(point.lat, point.lon, surface.artifact.resolution),
  );
  if (!cell) return { height: 0, triangle: null };
  const domain = surface.artifact.metric_domains[metric];
  const flatHeight = heightForCell(cell, domain, 1, metric);
  const supported =
    cell.support === 'observed' || cell.support === 'interpolated';
  if (!SMOOTH_GEOMETRIES.has(geometry) || !supported)
    return { height: flatHeight, triangle: null };
  const sample = triangleAtPoint(
    surfaceMeshForCell(cell, context.vertexHeights, domain, metric),
    point,
  );
  return {
    height: sample.weights.reduce(
      (height, weight, index) =>
        height + sample.triangle[index].height * weight,
      0,
    ),
    triangle: sample.triangle,
  };
}
