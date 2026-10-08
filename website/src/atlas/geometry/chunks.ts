/** Spatial chunk plan for progressive surface reveal (fast-load spec
 * 2026-10-07 §B.6.5 "Chunks", §B.6.7 ordering).
 *
 * The plan depends only on the grid, so every artifact on the shared grid
 * reuses it. Rule: seed one group per H3 base cell (a base cell whose cell
 * centres reach both east of +90° and west of -90° is split by the sign of
 * each centre's longitude); walking groups in base-cell order, greedily absorb
 * the first adjacent unassigned group (`gridDisk(base, 1)`) that keeps the
 * chunk on one side of ±180° and within CHUNK_MAX_RADIUS_METRES, until the
 * chunk holds CHUNK_MIN_CELLS cells. Cells whose own boundary crosses ±180°
 * go into dedicated seam chunks, one per side and hemisphere.
 */

import { getBaseCellNumber, getRes0Cells, gridDisk } from 'h3-js';

import type { DecodedGrid } from '../gosa/types';
import { crossesAntimeridian } from './polygon-parts';
import { cellLanes, type GridTopology } from './topology';
import {
  geodeticToEcef,
  scaleToGeocentricSurface,
  surfacePointToDegrees,
} from './wgs84';

export const CHUNK_MIN_CELLS = 2048;
/** Merge cap on the group-bound chunk radius (centre to farthest cell centre). */
export const CHUNK_MAX_RADIUS_METRES = 1_800_000;

export interface PlannedChunk {
  id: number;
  rows: Uint32Array;
  seam: boolean;
  centroid: { lat: number; lon: number };
}

export interface ChunkPlan {
  chunks: PlannedChunk[];
}

interface Group {
  base: number;
  rows: number[];
  centroid: [number, number, number];
  radius: number;
  east: boolean;
  west: boolean;
}

function makeGroup(
  base: number,
  rows: number[],
  centres: Float64Array,
  centreLon: Float64Array,
): Group {
  let x = 0;
  let y = 0;
  let z = 0;
  let east = false;
  let west = false;
  for (const row of rows) {
    x += centres[row * 3];
    y += centres[row * 3 + 1];
    z += centres[row * 3 + 2];
    if (centreLon[row] > 90) east = true;
    if (centreLon[row] < -90) west = true;
  }
  const centroid: [number, number, number] = [
    x / rows.length,
    y / rows.length,
    z / rows.length,
  ];
  let radius = 0;
  for (const row of rows)
    radius = Math.max(
      radius,
      Math.hypot(
        centres[row * 3] - centroid[0],
        centres[row * 3 + 1] - centroid[1],
        centres[row * 3 + 2] - centroid[2],
      ),
    );
  return { base, centroid, east, radius, rows, west };
}

function boundRadius(members: readonly Group[]): number {
  let count = 0;
  let x = 0;
  let y = 0;
  let z = 0;
  for (const group of members) {
    count += group.rows.length;
    x += group.centroid[0] * group.rows.length;
    y += group.centroid[1] * group.rows.length;
    z += group.centroid[2] * group.rows.length;
  }
  const centre = [x / count, y / count, z / count];
  let radius = 0;
  for (const group of members)
    radius = Math.max(
      radius,
      Math.hypot(
        group.centroid[0] - centre[0],
        group.centroid[1] - centre[1],
        group.centroid[2] - centre[2],
      ) + group.radius,
    );
  return radius;
}

function centroidOf(
  rows: readonly number[],
  centres: Float64Array,
): { lat: number; lon: number } {
  let x = 0;
  let y = 0;
  let z = 0;
  for (const row of rows) {
    x += centres[row * 3];
    y += centres[row * 3 + 1];
    z += centres[row * 3 + 2];
  }
  return surfacePointToDegrees(scaleToGeocentricSurface([x, y, z]));
}

let baseNeighbours: Map<number, ReadonlySet<number>> | null = null;

function neighboursOfBase(base: number): ReadonlySet<number> {
  if (!baseNeighbours) {
    baseNeighbours = new Map();
    for (const cell of getRes0Cells())
      baseNeighbours.set(
        getBaseCellNumber(cell),
        new Set(
          gridDisk(cell, 1)
            .map((neighbour) => getBaseCellNumber(neighbour))
            .filter((neighbour) => neighbour !== getBaseCellNumber(cell)),
        ),
      );
  }
  const neighbours = baseNeighbours.get(base);
  if (!neighbours) throw new Error(`unknown H3 base cell ${base}`);
  return neighbours;
}

export function planChunks(
  grid: DecodedGrid,
  topology: GridTopology,
): ChunkPlan {
  const n = grid.n;
  const centres = new Float64Array(n * 3);
  const seamRows: number[] = [];
  const byBase = new Map<number, number[]>();
  for (let row = 0; row < n; row += 1) {
    geodeticToEcef(
      topology.centreLon[row],
      topology.centreLat[row],
      0,
      centres,
      row * 3,
    );
    const cell = cellLanes(grid, row);
    if (crossesAntimeridian(cell)) {
      seamRows.push(row);
      continue;
    }
    const base = getBaseCellNumber(cell);
    const rows = byBase.get(base);
    if (rows) rows.push(row);
    else byBase.set(base, [row]);
  }

  const groups: Group[] = [];
  for (const base of [...byBase.keys()].sort((left, right) => left - right)) {
    const rows = byBase.get(base)!;
    const whole = makeGroup(base, rows, centres, topology.centreLon);
    if (!(whole.east && whole.west)) {
      groups.push(whole);
      continue;
    }
    const west = rows.filter((row) => topology.centreLon[row] < 0);
    const east = rows.filter((row) => topology.centreLon[row] >= 0);
    if (west.length > 0)
      groups.push(makeGroup(base, west, centres, topology.centreLon));
    if (east.length > 0)
      groups.push(makeGroup(base, east, centres, topology.centreLon));
  }

  const chunks: PlannedChunk[] = [];
  const assigned = new Array<boolean>(groups.length).fill(false);
  for (let seed = 0; seed < groups.length; seed += 1) {
    if (assigned[seed]) continue;
    assigned[seed] = true;
    const members = [groups[seed]];
    let count = groups[seed].rows.length;
    let east = groups[seed].east;
    let west = groups[seed].west;
    while (count < CHUNK_MIN_CELLS) {
      let pick = -1;
      for (let candidate = 0; candidate < groups.length; candidate += 1) {
        if (assigned[candidate]) continue;
        const group = groups[candidate];
        const adjacent = members.some(
          (member) =>
            member.base !== group.base &&
            neighboursOfBase(member.base).has(group.base),
        );
        if (!adjacent) continue;
        if ((east || group.east) && (west || group.west)) continue;
        if (boundRadius([...members, group]) > CHUNK_MAX_RADIUS_METRES)
          continue;
        pick = candidate;
        break;
      }
      if (pick < 0) break;
      assigned[pick] = true;
      members.push(groups[pick]);
      count += groups[pick].rows.length;
      east ||= groups[pick].east;
      west ||= groups[pick].west;
    }
    const rows = members.flatMap((member) => member.rows).sort((a, b) => a - b);
    chunks.push({
      centroid: centroidOf(rows, centres),
      id: chunks.length,
      rows: Uint32Array.from(rows),
      seam: false,
    });
  }

  const seamKeys = new Map<number, number[]>();
  for (const row of seamRows) {
    const key =
      (topology.centreLon[row] < 0 ? 0 : 2) +
      (topology.centreLat[row] < 0 ? 0 : 1);
    const rows = seamKeys.get(key);
    if (rows) rows.push(row);
    else seamKeys.set(key, [row]);
  }
  for (const key of [0, 1, 2, 3]) {
    const rows = seamKeys.get(key);
    if (!rows) continue;
    chunks.push({
      centroid: centroidOf(rows, centres),
      id: chunks.length,
      rows: Uint32Array.from(rows),
      seam: true,
    });
  }
  return { chunks };
}

/** Chunk ids, nearest centroid to the camera look-at point first (ties by id). */
export function orderChunksForCamera(
  plan: ChunkPlan,
  lookAt: { lat: number; lon: number },
): number[] {
  const target = [0, 0, 0];
  geodeticToEcef(lookAt.lon, lookAt.lat, 0, target);
  const point = [0, 0, 0];
  const distance = new Map<number, number>();
  for (const chunk of plan.chunks) {
    geodeticToEcef(chunk.centroid.lon, chunk.centroid.lat, 0, point);
    distance.set(
      chunk.id,
      Math.hypot(
        point[0] - target[0],
        point[1] - target[1],
        point[2] - target[2],
      ),
    );
  }
  return plan.chunks
    .map((chunk) => chunk.id)
    .sort(
      (left, right) =>
        distance.get(left)! - distance.get(right)! || left - right,
    );
}
