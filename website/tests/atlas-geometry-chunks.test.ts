import {
  cellToChildren,
  cellToLatLng,
  getBaseCellNumber,
  getRes0Cells,
  gridDisk,
} from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  CHUNK_MIN_CELLS,
  orderChunksForCamera,
  planChunks,
  type ChunkPlan,
} from '../src/atlas/geometry/chunks';
import { crossesAntimeridian } from '../src/atlas/geometry/polygon-parts';
import { buildGridTopology } from '../src/atlas/geometry/topology';
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
    const order = orderChunksForCamera(result, { lat: -17, lon: 179 });
    expect(order).toHaveLength(result.chunks.length);
    expect(new Set(order).size).toBe(result.chunks.length);
    const first = result.chunks[order[0]];
    expect(first.centroid.lat).toBeLessThan(0);
    expect(first.centroid.lon).toBeGreaterThan(0);
  });
});
