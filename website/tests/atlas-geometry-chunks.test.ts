import {
  cellToCenterChild,
  cellToChildren,
  cellToLatLng,
  cellToParent,
  getBaseCellNumber,
  getRes0Cells,
  greatCircleDistance,
  gridDisk,
} from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  CHUNK_MAX_RADIUS_METRES,
  CHUNK_MIN_CELLS,
  orderChunksForCamera,
  planChunks,
  type ChunkPlan,
  type PlannedChunk,
} from '../src/atlas/geometry/chunks';
import { crossesAntimeridian } from '../src/atlas/geometry/polygon-parts';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import { geodeticToEcef } from '../src/atlas/geometry/wgs84';
import {
  PARITY_DIR,
  decodedGridFromH3,
  sortedU64,
  surfaceFixturesIn,
} from './helpers/atlas-geometry';

function plan(cells: readonly string[]): ChunkPlan {
  const grid = decodedGridFromH3(cells);
  return planChunks(grid, buildGridTopology(grid));
}

function everyRowOnce(result: ChunkPlan, n: number): void {
  const seen = new Uint8Array(n);
  for (const chunk of result.chunks)
    for (const row of chunk.rows) seen[row] += 1;
  expect([...seen].every((count) => count === 1)).toBe(true);
}

function chunkCells(result: ChunkPlan, cells: readonly string[]): string[][] {
  return result.chunks.map((chunk) => [...chunk.rows].map((row) => cells[row]));
}

type Point = [number, number, number];

function groundCentre(cell: string): Point {
  const [lat, lon] = cellToLatLng(cell);
  const point: Point = [0, 0, 0];
  geodeticToEcef(lon, lat, 0, point);
  return point;
}

function meanOf(points: readonly Point[]): Point {
  const sum: Point = [0, 0, 0];
  for (const point of points)
    for (let axis = 0; axis < 3; axis += 1) sum[axis] += point[axis];
  return [
    sum[0] / points.length,
    sum[1] / points.length,
    sum[2] / points.length,
  ];
}

function distance(left: Point, right: Point): number {
  return Math.hypot(left[0] - right[0], left[1] - right[1], left[2] - right[2]);
}

/** Cell-weighted centroid to the farthest cell centre: the exact radius. */
function exactRadius(cells: readonly string[]): number {
  const points = cells.map(groundCentre);
  const centre = meanOf(points);
  return Math.max(...points.map((point) => distance(point, centre)));
}

/** §B.6.5's group-bound radius: centroid distance plus each group's radius. */
function groupBoundRadius(groups: readonly (readonly string[])[]): number {
  const centre = meanOf(groups.flat().map(groundCentre));
  return Math.max(
    ...groups.map(
      (group) =>
        distance(meanOf(group.map(groundCentre)), centre) + exactRadius(group),
    ),
  );
}

function adjacentBaseCells(left: string, right: string): boolean {
  const base = cellToParent(left, 0);
  const other = cellToParent(right, 0);
  return base !== other && gridDisk(base, 1).includes(other);
}

function chunkAt(id: number, lat: number, lon: number): PlannedChunk {
  return { centroid: { lat, lon }, id, rows: Uint32Array.of(id), seam: false };
}

// Res-4 cells whose own boundary crosses ±180°, from the shared grid: two north
// of the equator east and west, two south east and west.
const SEAM_CELLS = [
  '84045b3ffffffff',
  '840d865ffffffff',
  '849b401ffffffff',
  '849b40dffffffff',
];
// Ordinary res-4 cells next to them on either side.
const NEAR_SEAM = sortedU64(
  SEAM_CELLS.flatMap((cell) => gridDisk(cell, 1)),
).filter((cell) => !crossesAntimeridian(cell));

describe('chunk plan (fast-load §B.6.5 "Chunks")', () => {
  it('assigns every row of the parity subset to exactly one chunk', () => {
    const [fixture] = surfaceFixturesIn(PARITY_DIR);
    const result = planChunks(fixture.grid, buildGridTopology(fixture.grid));
    everyRowOnce(result, fixture.grid.n);
    result.chunks.forEach((chunk, index) => {
      expect(chunk.id).toBe(index);
      expect([...chunk.rows]).toEqual([...chunk.rows].sort((a, b) => a - b));
    });
  });

  it('is deterministic', () => {
    const cells = sortedU64(cellToChildren(getRes0Cells()[20], 2));
    expect(plan(cells)).toEqual(plan(cells));
  });

  it('keeps a full base cell whole and merges small adjacent groups', () => {
    const [base] = getRes0Cells().filter(
      (cell) => getBaseCellNumber(cell) === 20,
    );
    const neighbour = gridDisk(base, 1).find(
      (cell) => getBaseCellNumber(cell) > 20,
    )!;
    const large = cellToChildren(base, 4);
    expect(large.length).toBeGreaterThanOrEqual(CHUNK_MIN_CELLS);
    const across = cellToChildren(neighbour, 4).slice(0, 10);
    const full = plan(sortedU64([...large, ...across]));
    expect(
      full.chunks.map((chunk) => chunk.rows.length).sort((a, b) => a - b),
    ).toEqual([across.length, large.length]);

    const border = large.find((cell) =>
      gridDisk(cell, 1).some((near) => getBaseCellNumber(near) !== 20),
    )!;
    const patch = sortedU64(gridDisk(border, 3));
    expect(
      new Set(patch.map((cell) => getBaseCellNumber(cell))).size,
    ).toBeGreaterThan(1);
    const merged = plan(patch);
    expect(merged.chunks).toHaveLength(1);
    expect(merged.chunks[0].rows).toHaveLength(patch.length);
  });

  it('refuses every merge that would pass CHUNK_MAX_RADIUS_METRES', () => {
    // The centre cell of base cell 58 (near 0°, 0°) and of each of its five
    // neighbours: one run of adjacent base cells, all well inside ±90° and far
    // below CHUNK_MIN_CELLS, so without the cap they would merge into one chunk.
    const [base] = getRes0Cells().filter(
      (cell) => getBaseCellNumber(cell) === 58,
    );
    const cells = sortedU64(
      gridDisk(base, 1).map((cell) => cellToCenterChild(cell, 4)),
    );
    expect(cells).toHaveLength(6);
    expect(cells.every((cell) => Math.abs(cellToLatLng(cell)[1]) < 90)).toBe(
      true,
    );
    const result = plan(cells);
    everyRowOnce(result, cells.length);
    expect(result.chunks.length).toBeGreaterThan(1);
    expect(result.chunks.some((chunk) => chunk.rows.length > 1)).toBe(true);

    // One cell per group, so the group-bound radius is the exact radius.
    const members = chunkCells(result, cells);
    let refused = 0;
    members.forEach((chunk, index) => {
      expect(exactRadius(chunk)).toBeLessThanOrEqual(CHUNK_MAX_RADIUS_METRES);
      // A group adjacent to this chunk but left for a later chunk was refused
      // by the cap, since neither CHUNK_MIN_CELLS nor ±180° stopped the merge.
      for (const later of members.slice(index + 1).flat()) {
        if (!chunk.some((cell) => adjacentBaseCells(cell, later))) continue;
        refused += 1;
        expect(exactRadius([...chunk, later])).toBeGreaterThan(
          CHUNK_MAX_RADIUS_METRES,
        );
      }
    });
    expect(refused).toBeGreaterThan(0);
  });

  it('applies the cap to the group-bound radius, not the exact radius', () => {
    // Two res-2 cells at opposite ends of base cell 42 and two at opposite ends
    // of its neighbour 58. Each group's own radius is large, so the group bound
    // passes the cap although every cell centre lies within the cap of the
    // merged centroid.
    const inBase42 = ['825497fffffffff', '825547fffffffff'];
    const inBase58 = ['827497fffffffff', '8274d7fffffffff'];
    expect(inBase42.map((cell) => getBaseCellNumber(cell))).toEqual([42, 42]);
    expect(inBase58.map((cell) => getBaseCellNumber(cell))).toEqual([58, 58]);
    expect(adjacentBaseCells(inBase42[0], inBase58[0])).toBe(true);
    const cells = sortedU64([...inBase42, ...inBase58]);
    expect(exactRadius(cells)).toBeLessThanOrEqual(CHUNK_MAX_RADIUS_METRES);
    expect(groupBoundRadius([inBase42, inBase58])).toBeGreaterThan(
      CHUNK_MAX_RADIUS_METRES,
    );
    expect(chunkCells(plan(cells), cells)).toEqual([inBase42, inBase58]);
  });

  it('puts boundary-crossing cells into seam chunks by side and hemisphere', () => {
    const cells = sortedU64([...SEAM_CELLS, ...NEAR_SEAM]);
    const result = plan(cells);
    everyRowOnce(result, cells.length);
    const seams = result.chunks.filter((chunk) => chunk.seam);
    expect(seams).toHaveLength(4);
    const seamCells = seams.flatMap((chunk) =>
      [...chunk.rows].map((row) => cells[row]),
    );
    expect(sortedU64(seamCells)).toEqual(sortedU64(SEAM_CELLS));
    for (const chunk of seams) {
      const signs = [...chunk.rows].map((row) => {
        const [lat, lon] = cellToLatLng(cells[row]);
        return `${Math.sign(lat)}:${lon < 0 ? -1 : 1}`;
      });
      expect(new Set(signs).size).toBe(1);
    }
  });

  it('never lets an ordinary chunk straddle ±180°', () => {
    const cells = sortedU64([...SEAM_CELLS, ...NEAR_SEAM]);
    for (const chunk of plan(cells).chunks.filter((entry) => !entry.seam)) {
      const longitudes = [...chunk.rows].map(
        (row) => cellToLatLng(cells[row])[1],
      );
      expect(
        longitudes.some((lon) => lon > 90) &&
          longitudes.some((lon) => lon < -90),
      ).toBe(false);
    }
  });

  it('orders chunks nearest to the look-at point first', () => {
    const cells = sortedU64([...SEAM_CELLS, ...NEAR_SEAM]);
    const result = plan(cells);
    const lookAt = { lat: -17, lon: 179 };
    const order = orderChunksForCamera(result, lookAt);
    expect([...order].sort((left, right) => left - right)).toEqual(
      result.chunks.map((chunk) => chunk.id),
    );
    const first = result.chunks[order[0]];
    expect(first.centroid.lat).toBeLessThan(0);
    expect(first.centroid.lon).toBeGreaterThan(0);
    // The whole order, checked against an independent (great-circle) distance:
    // strictly increasing, so it is the only nearest-first order.
    const kilometres = order.map((id) =>
      greatCircleDistance(
        [lookAt.lat, lookAt.lon],
        [result.chunks[id].centroid.lat, result.chunks[id].centroid.lon],
        'km',
      ),
    );
    kilometres
      .slice(1)
      .forEach((next, index) =>
        expect(next).toBeGreaterThan(kilometres[index]),
      );
  });

  it('breaks equal camera distances by chunk id', () => {
    // Centroids mirrored about the look-at point tie exactly (±10° of longitude
    // on the equator, ±20° of latitude on the meridian). The chunks are listed
    // out of id order, so a stable sort without the id tie-break fails.
    const shuffled: ChunkPlan = {
      chunks: [
        chunkAt(5, -20, 0),
        chunkAt(3, 0, 10),
        chunkAt(0, 0, 40),
        chunkAt(4, 20, 0),
        chunkAt(1, 0, -10),
        chunkAt(2, 0, 0),
      ],
    };
    expect(orderChunksForCamera(shuffled, { lat: 0, lon: 0 })).toEqual([
      2, 1, 3, 4, 5, 0,
    ]);
  });
});
