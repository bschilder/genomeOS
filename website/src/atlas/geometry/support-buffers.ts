/** Worker-built support (mask) buffers per chunk (fast-load spec 2026-10-07
 * §B.6.5 "Support (mask) geometry", §B.7 support materials).
 *
 * Unknown cells feed the existing `Grid` material and prior-dominated cells
 * the `Dot` material of their palette bin; both need per-cell `st` in [0, 1].
 * Each H3 polygon part (pole-enclosing cells keep the legacy fan split) is
 * triangulated around the cell centre at SURFACE_CLEARANCE_METRES. Normals are
 * `Ellipsoid.WGS84.geodeticSurfaceNormal` of each raised position, as on
 * Cesium's PolygonGeometry top face.
 *
 * `st` repeats the texture frame Cesium 1.145's PolygonGeometry gives a part
 * whose rectangle spans less than π (stRotation 0): the east/north tangent
 * plane at the centre of the ring's ground-level bounding box, each ground
 * point projected onto it along its geocentric ray, then normalised over the
 * ring. One step is simplified: the plane normal is taken at the box centre
 * itself, where Cesium first scales that centre to the geodetic surface. Both
 * points share a longitude, so east is unchanged; the normal tilts by under
 * 2e-7 rad, and st matches PolygonGeometry to float32 rounding from the
 * equator to 85° and across ±180° (atlas-geometry-support.test.ts). Cesium
 * switches to a stereographic projection for a part spanning π or more (one
 * split triangle of each pole-enclosing cell); that part keeps the tangent
 * plane here.
 */

import { cellToLatLng } from 'h3-js';

import type { PlannedChunk } from './chunks';
import { h3PolygonParts } from './polygon-parts';
import {
  indexArrayFor,
  paletteBins,
  SURFACE_CLEARANCE_METRES,
  type MeshInput,
} from './surface-buffers';
import { PRIOR_DOMINATED_CODE, UNKNOWN_CODE } from './support-codes';
import { cellLanes } from './topology';
import {
  boundingSphereOf,
  geodeticSurfaceNormal,
  geodeticToEcef,
  type BoundingSphere,
  type Vec3,
} from './wgs84';

export interface FlatCellBuffers {
  positions: Float64Array;
  normals: Float32Array;
  st: Float32Array;
  indices: Uint16Array | Uint32Array;
  boundingSphere: BoundingSphere;
}

export interface SupportChunkBuffers {
  chunk: number;
  unknown: FlatCellBuffers | null;
  priorDominated: {
    bin: number;
    color: [number, number, number];
    buffers: FlatCellBuffers;
  }[];
}

interface Part {
  points: [number, number][];
  fanCentre: [number, number] | null;
}

function partsForRow(input: MeshInput, row: number): Part[] {
  const cell = cellLanes(input.grid, row);
  const [centreLat, centreLon] = cellToLatLng(cell);
  return h3PolygonParts(cell).map((points) => ({
    fanCentre: points.length === 3 ? null : [centreLon, centreLat],
    points,
  }));
}

/** `EllipsoidTangentPlane.fromPoints(ring)`, its normal taken at the box
 * centre (module comment). */
interface TangentPlane {
  origin: Vec3;
  east: Vec3;
  north: Vec3;
  up: Vec3;
}

function dot(left: Vec3, right: Vec3): number {
  return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

function tangentPlaneOf(ring: readonly Vec3[]): TangentPlane {
  const min: Vec3 = [...ring[0]];
  const max: Vec3 = [...ring[0]];
  for (const point of ring)
    for (let axis = 0; axis < 3; axis += 1) {
      if (point[axis] < min[axis]) min[axis] = point[axis];
      if (point[axis] > max[axis]) max[axis] = point[axis];
    }
  const origin: Vec3 = [
    (min[0] + max[0]) * 0.5,
    (min[1] + max[1]) * 0.5,
    (min[2] + max[2]) * 0.5,
  ];
  const up = geodeticSurfaceNormal(origin);
  const length = Math.sqrt(origin[0] * origin[0] + origin[1] * origin[1]);
  const east: Vec3 = [-origin[1] / length, origin[0] / length, 0];
  const north: Vec3 = [
    up[1] * east[2] - up[2] * east[1],
    up[2] * east[0] - up[0] * east[2],
    up[0] * east[1] - up[1] * east[0],
  ];
  return { east, north, origin, up };
}

/** `EllipsoidTangentPlane.projectPointOntoPlane`: along the geocentric ray. */
function projectOntoPlane(plane: TangentPlane, point: Vec3): [number, number] {
  const scale = dot(plane.up, plane.origin) / dot(plane.up, point);
  const offset: Vec3 = [
    point[0] * scale - plane.origin[0],
    point[1] * scale - plane.origin[1],
    point[2] * scale - plane.origin[2],
  ];
  return [dot(plane.east, offset), dot(plane.north, offset)];
}

/** Flat buffers for `rows` (all from one grid), in row then part order. */
export function flatCellBuffers(
  input: MeshInput,
  rows: readonly number[],
): FlatCellBuffers {
  const parts = rows.flatMap((row) => partsForRow(input, row));
  let vertexCount = 0;
  let indexCount = 0;
  for (const part of parts) {
    vertexCount += part.points.length + (part.fanCentre ? 1 : 0);
    indexCount += part.fanCentre ? part.points.length * 3 : 3;
  }
  const positions = new Float64Array(vertexCount * 3);
  const normals = new Float32Array(vertexCount * 3);
  const st = new Float32Array(vertexCount * 2);
  const indices = new Array<number>(indexCount);
  let vertex = 0;
  let next = 0;
  for (const part of parts) {
    const corners = part.fanCentre
      ? [part.fanCentre, ...part.points]
      : part.points;
    const ground = corners.map(([lon, lat]) => {
      const point: Vec3 = [0, 0, 0];
      geodeticToEcef(lon, lat, 0, point);
      return point;
    });
    const ring = part.fanCentre ? ground.slice(1) : ground;
    const tangentPlane = tangentPlaneOf(ring);
    const plane = ground.map((point) => projectOntoPlane(tangentPlane, point));
    const ringPlane = part.fanCentre ? plane.slice(1) : plane;
    const minE = Math.min(...ringPlane.map(([e]) => e));
    const maxE = Math.max(...ringPlane.map(([e]) => e));
    const minN = Math.min(...ringPlane.map(([, n]) => n));
    const maxN = Math.max(...ringPlane.map(([, n]) => n));
    const first = vertex;
    corners.forEach(([lon, lat], index) => {
      geodeticToEcef(lon, lat, SURFACE_CLEARANCE_METRES, positions, vertex * 3);
      normals.set(
        geodeticSurfaceNormal(positions.subarray(vertex * 3, vertex * 3 + 3)),
        vertex * 3,
      );
      const [e, n] = plane[index];
      st[vertex * 2] = Math.min(1, Math.max(0, (e - minE) / (maxE - minE)));
      st[vertex * 2 + 1] = Math.min(1, Math.max(0, (n - minN) / (maxN - minN)));
      vertex += 1;
    });
    if (!part.fanCentre) {
      indices[next++] = first;
      indices[next++] = first + 1;
      indices[next++] = first + 2;
      continue;
    }
    const count = part.points.length;
    for (let corner = 0; corner < count; corner += 1) {
      indices[next++] = first;
      indices[next++] = first + 1 + corner;
      indices[next++] = first + 1 + ((corner + 1) % count);
    }
  }
  return {
    boundingSphere: boundingSphereOf([positions]),
    indices: indexArrayFor(vertexCount, indices),
    normals,
    positions,
    st,
  };
}

/** The chunk's masked cells: unknown (Grid) and prior-dominated per bin (Dot). */
export function buildSupportChunk(
  input: MeshInput,
  chunk: PlannedChunk,
): SupportChunkBuffers {
  const unknownRows: number[] = [];
  const priorRows = new Map<number, number[]>();
  const bins = paletteBins(input, 'prior_dominated');
  for (const row of chunk.rows) {
    const code = input.support[row];
    if (code === UNKNOWN_CODE) unknownRows.push(row);
    else if (code === PRIOR_DOMINATED_CODE) {
      const bin = bins.binOfRow[row];
      const rows = priorRows.get(bin);
      if (rows) rows.push(row);
      else priorRows.set(bin, [row]);
    }
  }
  return {
    chunk: chunk.id,
    priorDominated: [...priorRows.keys()]
      .sort((left, right) => left - right)
      .map((bin) => ({
        bin,
        buffers: flatCellBuffers(input, priorRows.get(bin)!),
        color: bins.colors.get(bin)!,
      })),
    unknown:
      unknownRows.length > 0 ? flatCellBuffers(input, unknownRows) : null,
  };
}
