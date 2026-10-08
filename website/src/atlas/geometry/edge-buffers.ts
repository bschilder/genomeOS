/** Worker-built cell-outline rings (fast-load spec 2026-10-07 §B.6.9).
 *
 * Rings reproduce the legacy `edgeDefinitionsForCell`: `h3PolygonParts`
 * boundaries closed by repeating the first point, 1,050 m above the ellipsoid
 * along the geocentric normal; smooth modes take each point's height from the
 * mesh vertex at the same 7-decimal coordinate (else the cell height, which is
 * what class-III distortion points get), flat modes use the cell height.
 */

import type { PlannedChunk } from './chunks';
import { h3PolygonParts } from './polygon-parts';
import {
  isSmoothGeometry,
  paletteBins,
  vertexMeans,
  type MeshInput,
} from './surface-buffers';
import { isSupportedCode, supportName } from './support-codes';
import { cellLanes } from './topology';
import { heightFor } from '../visual-encoding';
import { geodeticToEcef, normalizeInto } from './wgs84';

export const EDGE_CLEARANCE_METRES = 1_050;
const EDGE_ALPHA = 0.92;
const MATCHED_EDGE_LIGHTEN = 0.46;

export type EdgeColorSpec =
  { mode: 'matched' } | { mode: 'fixed'; color: string };

export interface EdgeChunkBuffers {
  chunk: number;
  /** Ring k's vertices are `ringOffsets[k] .. ringOffsets[k + 1]`. */
  ringOffsets: Uint32Array;
  /** Positions at the requested factor: base + normal × baseHeight × factor. */
  positions: Float64Array;
  basePositions: Float64Array;
  /** Mesh height under each ring vertex at exaggeration 1. */
  baseHeights: Float64Array;
  normals: Float32Array;
  /** RGBA per ring. */
  colors: Float32Array;
}

function coordinateKey(lon: number, lat: number): string {
  return `${lon.toFixed(7)}:${lat.toFixed(7)}`;
}

/** Cesium `Color.floatToByte`. */
function floatToByte(value: number): number {
  return value === 1.0 ? 255.0 : (value * 256.0) | 0;
}

/** `brighterEdgeColor`: lerp toward white by 0.46, then the CSS hex bytes. */
export function brighterEdgeBytes(
  bytes: readonly [number, number, number],
): [number, number, number] {
  return bytes.map((byte) => {
    const channel = byte / 255.0;
    return floatToByte(
      (1.0 - MATCHED_EDGE_LIGHTEN) * channel + MATCHED_EDGE_LIGHTEN * 1.0,
    );
  }) as [number, number, number];
}

function bytesFromHex(color: string): [number, number, number] {
  if (!/^#[0-9a-f]{6}$/i.test(color))
    throw new Error(`edge colour must be #rrggbb, got ${color}`);
  return [1, 3, 5].map((offset) =>
    Number.parseInt(color.slice(offset, offset + 2), 16),
  ) as [number, number, number];
}

export function buildEdgeChunk(
  input: MeshInput,
  chunk: PlannedChunk,
  edgeColor: EdgeColorSpec,
  factor = 0,
): EdgeChunkBuffers {
  const { topology, domain } = input;
  const smooth = isSmoothGeometry(input.geometry);
  const heights = smooth
    ? (input.vertexHeights ?? vertexMeans(input).heights)
    : null;
  const bins =
    edgeColor.mode === 'matched' ? paletteBins(input, 'supported') : null;
  const fixed =
    edgeColor.mode === 'fixed' ? bytesFromHex(edgeColor.color) : null;
  const rings: {
    points: [number, number][];
    heights: number[];
    color: [number, number, number];
  }[] = [];
  for (const row of chunk.rows) {
    const code = input.support[row];
    if (!isSupportedCode(code)) continue;
    const centerHeight = heightFor(
      supportName(code),
      input.values[row],
      domain,
      1,
    );
    const byCoordinate = new Map<string, number>();
    if (heights) {
      byCoordinate.set(
        coordinateKey(topology.centreLon[row], topology.centreLat[row]),
        centerHeight,
      );
      for (
        let corner = topology.cornerOffsets[row];
        corner < topology.cornerOffsets[row + 1];
        corner += 1
      ) {
        const id = topology.cornerIds[corner];
        byCoordinate.set(
          coordinateKey(topology.vertexLon[id], topology.vertexLat[id]),
          heights[id],
        );
      }
    }
    const color = bins
      ? brighterEdgeBytes(bins.colors.get(bins.binOfRow[row])!)
      : fixed!;
    for (const part of h3PolygonParts(cellLanes(input.grid, row))) {
      const points = [...part, part[0]];
      rings.push({
        color,
        heights: points.map(([lon, lat]) =>
          heights
            ? (byCoordinate.get(coordinateKey(lon, lat)) ?? centerHeight)
            : centerHeight,
        ),
        points,
      });
    }
  }
  const vertexCount = rings.reduce(
    (total, ring) => total + ring.points.length,
    0,
  );
  const ringOffsets = new Uint32Array(rings.length + 1);
  const positions = new Float64Array(vertexCount * 3);
  const basePositions = new Float64Array(vertexCount * 3);
  const baseHeights = new Float64Array(vertexCount);
  const normals = new Float32Array(vertexCount * 3);
  const colors = new Float32Array(rings.length * 4);
  const ground = new Float64Array(3);
  const normal = new Float64Array(3);
  let vertex = 0;
  rings.forEach((ring, index) => {
    ringOffsets[index] = vertex;
    colors.set(
      [
        ring.color[0] / 255,
        ring.color[1] / 255,
        ring.color[2] / 255,
        EDGE_ALPHA,
      ],
      index * 4,
    );
    ring.points.forEach(([lon, lat], point) => {
      geodeticToEcef(lon, lat, 0, ground);
      normalizeInto(ground, 0, normal);
      const offset = vertex * 3;
      baseHeights[vertex] = ring.heights[point];
      for (let axis = 0; axis < 3; axis += 1) {
        basePositions[offset + axis] =
          ground[axis] + normal[axis] * EDGE_CLEARANCE_METRES;
        normals[offset + axis] = normal[axis];
      }
      for (let axis = 0; axis < 3; axis += 1)
        positions[offset + axis] =
          basePositions[offset + axis] +
          normal[axis] * baseHeights[vertex] * factor;
      vertex += 1;
    });
  });
  ringOffsets[rings.length] = vertex;
  return {
    baseHeights,
    basePositions,
    chunk: chunk.id,
    colors,
    normals,
    positions,
    ringOffsets,
  };
}

/** Exact BufferPolylineCollection capacity over `buffers`. */
export function edgeCapacity(buffers: readonly EdgeChunkBuffers[]): {
  primitiveCountMax: number;
  vertexCountMax: number;
} {
  return {
    primitiveCountMax: buffers.reduce(
      (total, chunk) => total + chunk.ringOffsets.length - 1,
      0,
    ),
    vertexCountMax: buffers.reduce(
      (total, chunk) => total + chunk.baseHeights.length,
      0,
    ),
  };
}
