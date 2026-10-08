/** Worker-built support (mask) buffers per chunk (fast-load spec 2026-10-07
 * §B.6.5 "Support (mask) geometry", §B.7 support materials).
 *
 * Unknown cells feed the existing `Grid` material and prior-dominated cells
 * the `Dot` material of their palette bin; both need per-cell `st` in [0, 1].
 * Each H3 polygon part (pole-enclosing cells keep the legacy fan split) is
 * triangulated around the cell centre at SURFACE_CLEARANCE_METRES; `st` is
 * the part's east/north extent in the tangent plane at the cell centre, the
 * frame Cesium's PolygonGeometry uses for these small polygons.
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
import { boundingSphereOf, geodeticToEcef, type BoundingSphere } from './wgs84';

const RADIANS_PER_DEGREE = Math.PI / 180.0;

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
  originLon: number;
  originLat: number;
  fanCentre: [number, number] | null;
}

function partsForRow(input: MeshInput, row: number): Part[] {
  const cell = cellLanes(input.grid, row);
  const [centreLat, centreLon] = cellToLatLng(cell);
  return h3PolygonParts(cell).map((points) =>
    points.length === 3
      ? { fanCentre: null, originLat: centreLat, originLon: centreLon, points }
      : {
          fanCentre: [centreLon, centreLat],
          originLat: centreLat,
          originLon: centreLon,
          points,
        },
  );
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
    const lambda = part.originLon * RADIANS_PER_DEGREE;
    const phi = part.originLat * RADIANS_PER_DEGREE;
    const east = [-Math.sin(lambda), Math.cos(lambda), 0];
    const north = [
      -Math.sin(phi) * Math.cos(lambda),
      -Math.sin(phi) * Math.sin(lambda),
      Math.cos(phi),
    ];
    const origin = [0, 0, 0];
    geodeticToEcef(part.originLon, part.originLat, 0, origin);
    const corners = part.fanCentre
      ? [part.fanCentre, ...part.points]
      : part.points;
    const plane = corners.map(([lon, lat]) => {
      const ground = [0, 0, 0];
      geodeticToEcef(lon, lat, 0, ground);
      const delta = [
        ground[0] - origin[0],
        ground[1] - origin[1],
        ground[2] - origin[2],
      ];
      return [
        delta[0] * east[0] + delta[1] * east[1] + delta[2] * east[2],
        delta[0] * north[0] + delta[1] * north[1] + delta[2] * north[2],
      ];
    });
    const ring = part.fanCentre ? plane.slice(1) : plane;
    const minE = Math.min(...ring.map(([e]) => e));
    const maxE = Math.max(...ring.map(([e]) => e));
    const minN = Math.min(...ring.map(([, n]) => n));
    const maxN = Math.max(...ring.map(([, n]) => n));
    const first = vertex;
    corners.forEach(([lon, lat], index) => {
      geodeticToEcef(lon, lat, SURFACE_CLEARANCE_METRES, positions, vertex * 3);
      const lonRadians = lon * RADIANS_PER_DEGREE;
      const latRadians = lat * RADIANS_PER_DEGREE;
      normals[vertex * 3] = Math.cos(latRadians) * Math.cos(lonRadians);
      normals[vertex * 3 + 1] = Math.cos(latRadians) * Math.sin(lonRadians);
      normals[vertex * 3 + 2] = Math.sin(latRadians);
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
