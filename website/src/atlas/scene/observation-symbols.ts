/** Surface-mounted observation glyphs for Atlas design §11.
 *
 * Marker anchors are presentation-only samples of the active render mesh.
 * They never alter observation coordinates, sampling radii, or artifact data.
 */

import { latLngToCell } from 'h3-js';
import { Cartesian3, Ellipsoid } from 'cesium';

import type { SurfaceArtifact, SurfaceCell } from '../contracts';
import type { SurfaceGeometry } from '../url-state';
import { heightForCell, type Metric } from '../visual-encoding';
import {
  SURFACE_CLEARANCE_METRES,
  surfaceMeshForCell,
  surfaceVertexHeights,
  type SurfaceCellMesh,
  type SurfaceMeshVertex,
} from './surface-mesh';

export interface GeographicPoint {
  lat: number;
  lon: number;
}

export interface ObservationSurfaceAnchor {
  height: number;
  triangle:
    readonly [SurfaceMeshVertex, SurfaceMeshVertex, SurfaceMeshVertex] | null;
}

export interface ObservationSurfacePlacement {
  eyeOffset: Cartesian3;
  normal: Cartesian3;
  position: Cartesian3;
}

export interface ObservationSurfaceContext {
  cells: ReadonlyMap<string, SurfaceCell>;
  vertexHeights: ReadonlyMap<string, number>;
}

interface TriangleSample {
  triangle: readonly [SurfaceMeshVertex, SurfaceMeshVertex, SurfaceMeshVertex];
  weights: readonly [number, number, number];
}

export const STUD_ASPECT_RATIO = 0.72;
export const SYMBOL_CLEARANCE_METRES = 7_000;
export const SYMBOL_EYE_OFFSET_METRES = 1_200;

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
  surface: SurfaceArtifact,
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
  surface: SurfaceArtifact,
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

function raisedVertex(vertex: SurfaceMeshVertex, factor: number): Cartesian3 {
  return Cartesian3.fromDegrees(
    vertex.lon,
    vertex.lat,
    SURFACE_CLEARANCE_METRES + vertex.height * factor,
  );
}

function triangleNormal(
  triangle: NonNullable<ObservationSurfaceAnchor['triangle']>,
  factor: number,
  radial: Cartesian3,
): Cartesian3 {
  if (factor === 0) return radial;
  const first = raisedVertex(triangle[0], factor);
  const firstEdge = Cartesian3.subtract(
    raisedVertex(triangle[1], factor),
    first,
    new Cartesian3(),
  );
  const secondEdge = Cartesian3.subtract(
    raisedVertex(triangle[2], factor),
    first,
    new Cartesian3(),
  );
  const normal = Cartesian3.normalize(
    Cartesian3.cross(firstEdge, secondEdge, new Cartesian3()),
    new Cartesian3(),
  );
  if (Cartesian3.dot(normal, radial) < 0) Cartesian3.negate(normal, normal);
  return normal;
}

export function observationSurfacePlacement(
  anchor: ObservationSurfaceAnchor,
  point: GeographicPoint,
  elevationFactor: number,
): ObservationSurfacePlacement {
  const safeFactor = Math.max(0, elevationFactor);
  const position = Cartesian3.fromDegrees(
    point.lon,
    point.lat,
    SURFACE_CLEARANCE_METRES +
      anchor.height * safeFactor +
      SYMBOL_CLEARANCE_METRES,
  );
  const radial = Ellipsoid.WGS84.geodeticSurfaceNormal(
    position,
    new Cartesian3(),
  );
  return {
    eyeOffset: new Cartesian3(0, 0, -SYMBOL_EYE_OFFSET_METRES),
    normal: anchor.triangle
      ? triangleNormal(anchor.triangle, safeFactor, radial)
      : radial,
    position,
  };
}

const LIT_STUD_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" width="128" height="96" viewBox="0 0 128 96">
    <defs><radialGradient id="stud" cx="32%" cy="22%" r="76%">
      <stop offset="0" stop-color="white"/><stop offset="0.38" stop-color="#edf7ff" stop-opacity=".94"/>
      <stop offset="0.78" stop-color="#7d91a8" stop-opacity=".86"/><stop offset="1" stop-color="#101b2b" stop-opacity=".98"/>
    </radialGradient></defs>
    <ellipse cx="64" cy="87" rx="55" ry="9" fill="#020712" fill-opacity=".32"/>
    <path d="M9 84C12 38 33 8 64 8S116 38 119 84C105 94 23 94 9 84Z" fill="url(#stud)"/>
    <ellipse cx="64" cy="84" rx="55" ry="10" fill="none" stroke="white" stroke-opacity=".38" stroke-width="2"/>
    <ellipse cx="46" cy="30" rx="15" ry="9" fill="white" fill-opacity=".24"/>
  </svg>
`)}`;

export function litStudImage(): HTMLCanvasElement | string {
  if (typeof document === 'undefined') return LIT_STUD_IMAGE;
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 96;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas rendering is required for studs.');
  context.fillStyle = 'rgba(2, 7, 18, 0.32)';
  context.beginPath();
  context.ellipse(64, 87, 55, 9, 0, 0, Math.PI * 2);
  context.fill();
  context.beginPath();
  context.moveTo(9, 84);
  context.bezierCurveTo(12, 38, 33, 8, 64, 8);
  context.bezierCurveTo(95, 8, 116, 38, 119, 84);
  context.bezierCurveTo(105, 94, 23, 94, 9, 84);
  context.closePath();
  const body = context.createRadialGradient(41, 23, 2, 64, 55, 60);
  body.addColorStop(0, 'rgba(255, 255, 255, 1)');
  body.addColorStop(0.38, 'rgba(237, 247, 255, 0.94)');
  body.addColorStop(0.78, 'rgba(125, 145, 168, 0.86)');
  body.addColorStop(1, 'rgba(16, 27, 43, 0.98)');
  context.fillStyle = body;
  context.fill();
  context.strokeStyle = 'rgba(255, 255, 255, 0.38)';
  context.lineWidth = 2;
  context.beginPath();
  context.ellipse(64, 84, 55, 10, 0, 0, Math.PI * 2);
  context.stroke();
  return canvas;
}
