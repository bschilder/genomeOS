/** Surface-mounted observation glyphs for Atlas design §11.
 *
 * Marker anchors are presentation-only samples of the active render mesh.
 * They never alter observation coordinates, sampling radii, or artifact data.
 */

import { Cartesian3, Ellipsoid } from 'cesium';

import type { ObservationAnchorBuffers } from '../worker/protocol';
import { SURFACE_CLEARANCE_METRES } from './surface-appearance';

export interface GeographicPoint {
  lat: number;
  lon: number;
}

export interface AnchorVertex {
  height: number;
  lat: number;
  lon: number;
}

export interface ObservationSurfaceAnchor {
  height: number;
  triangle: readonly [AnchorVertex, AnchorVertex, AnchorVertex] | null;
}

export interface ObservationSurfaceHeights {
  anchors: readonly ObservationSurfaceAnchor[];
  ringBaseHeights: readonly number[];
}

export interface ObservationSurfacePlacement {
  eyeOffset: Cartesian3;
  normal: Cartesian3;
  position: Cartesian3;
}

export interface SphereSurfacePlacement {
  center: Cartesian3;
  radii: Cartesian3;
  radiusMetres: number;
}

export const STUD_ASPECT_RATIO = 0.72;
export const SYMBOL_CLEARANCE_METRES = 7_000;
export const SYMBOL_EYE_OFFSET_METRES = 1_200;
export const SPHERE_METRES_PER_SIZE_UNIT = 1_000;

function raisedVertex(vertex: AnchorVertex, factor: number): Cartesian3 {
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

export function sphereSurfacePlacement(
  placement: ObservationSurfacePlacement,
  size: number,
): SphereSurfacePlacement {
  const radiusMetres = size * SPHERE_METRES_PER_SIZE_UNIT;
  return {
    center: Cartesian3.add(
      placement.position,
      Cartesian3.multiplyByScalar(
        placement.normal,
        radiusMetres,
        new Cartesian3(),
      ),
      new Cartesian3(),
    ),
    radii: new Cartesian3(radiusMetres, radiusMetres, radiusMetres),
    radiusMetres,
  };
}

const LIT_STUD_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" width="128" height="96" viewBox="0 0 128 96">
    <defs><radialGradient id="stud" cx="32%" cy="22%" r="76%">
      <stop offset="0" stop-color="white"/><stop offset="0.38" stop-color="#edf7ff"/>
      <stop offset="0.78" stop-color="#7d91a8"/><stop offset="1" stop-color="#101b2b"/>
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
  body.addColorStop(0.38, 'rgba(237, 247, 255, 1)');
  body.addColorStop(0.78, 'rgba(125, 145, 168, 1)');
  body.addColorStop(1, 'rgba(16, 27, 43, 1)');
  context.fillStyle = body;
  context.fill();
  context.strokeStyle = 'rgba(255, 255, 255, 0.38)';
  context.lineWidth = 2;
  context.beginPath();
  context.ellipse(64, 84, 55, 10, 0, 0, Math.PI * 2);
  context.stroke();
  return canvas;
}

/** Worker anchors (spec §B.6.5): never computed from the detail tier. */
export function anchorsFromBuffers(
  buffers: ObservationAnchorBuffers,
  count: number,
): ObservationSurfaceAnchor[] {
  if (
    buffers.heights.length !== count ||
    buffers.triangles.length !== count * 9
  )
    throw new Error(
      `Observation anchors do not match the ${count} observations of this artifact`,
    );
  return Array.from({ length: count }, (_, index) => {
    const offset = index * 9;
    const triangle = Number.isNaN(buffers.triangles[offset])
      ? null
      : ([0, 1, 2].map((vertex) => ({
          height: buffers.triangles[offset + vertex * 3 + 2],
          lat: buffers.triangles[offset + vertex * 3],
          lon: buffers.triangles[offset + vertex * 3 + 1],
        })) as [AnchorVertex, AnchorVertex, AnchorVertex]);
    return { height: buffers.heights[index], triangle };
  });
}
