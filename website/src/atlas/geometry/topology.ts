/** Shared-grid H3 topology for the Atlas data worker (fast-load spec
 * 2026-10-07 §B.6.4–§B.6.5).
 *
 * Built once per grid from the u32 lanes. Vertex ids are dense integers in
 * first-seen order (grid row order, then `cellToVertexes` order), so every
 * artifact on the grid shares them. The mesh uses `cellToVertexes` corners
 * only; class-III distortion points from `cellToBoundary` are used by support
 * and edge rings, exactly as the legacy builder does.
 */

import {
  cellToLatLng,
  cellToVertexes,
  h3IndexToSplitLong,
  vertexToLatLng,
} from 'h3-js';

import type { DecodedGrid } from '../gosa/types';

export interface GridTopology {
  n: number;
  centreLat: Float64Array;
  centreLon: Float64Array;
  /** Row r's corners are `cornerIds[cornerOffsets[r] .. cornerOffsets[r + 1])`. */
  cornerOffsets: Uint32Array;
  cornerIds: Uint32Array;
  vertexLat: Float64Array;
  vertexLon: Float64Array;
}

/** The row's index as the `[low, high]` u32 pair h3-js accepts. */
export function cellLanes(grid: DecodedGrid, row: number): [number, number] {
  return [grid.h3Lo[row], grid.h3Hi[row]];
}

export function buildGridTopology(grid: DecodedGrid): GridTopology {
  const n = grid.n;
  const centreLat = new Float64Array(n);
  const centreLon = new Float64Array(n);
  const cornerOffsets = new Uint32Array(n + 1);
  const corners: number[] = [];
  const vertexIds = new Map<string, number>();
  const vertexLat: number[] = [];
  const vertexLon: number[] = [];
  for (let row = 0; row < n; row += 1) {
    const cell = cellLanes(grid, row);
    const [lat, lon] = cellToLatLng(cell);
    centreLat[row] = lat;
    centreLon[row] = lon;
    for (const vertex of cellToVertexes(cell)) {
      let id = vertexIds.get(vertex);
      if (id === undefined) {
        id = vertexLat.length;
        vertexIds.set(vertex, id);
        const [vertexLatitude, vertexLongitude] = vertexToLatLng(vertex);
        vertexLat.push(vertexLatitude);
        vertexLon.push(vertexLongitude);
      }
      corners.push(id);
    }
    cornerOffsets[row + 1] = corners.length;
  }
  return {
    centreLat,
    centreLon,
    cornerIds: Uint32Array.from(corners),
    cornerOffsets,
    n,
    vertexLat: Float64Array.from(vertexLat),
    vertexLon: Float64Array.from(vertexLon),
  };
}

/** Binary search of the sorted grid; `null` when the cell is not on it. */
export function gridRowOf(grid: DecodedGrid, h3Index: string): number | null {
  const [low, high] = h3IndexToSplitLong(h3Index);
  let first = 0;
  let last = grid.n - 1;
  while (first <= last) {
    const middle = (first + last) >>> 1;
    const middleHigh = grid.h3Hi[middle];
    const middleLow = grid.h3Lo[middle];
    if (middleHigh === high && middleLow === low) return middle;
    if (middleHigh < high || (middleHigh === high && middleLow < low))
      first = middle + 1;
    else last = middle - 1;
  }
  return null;
}
