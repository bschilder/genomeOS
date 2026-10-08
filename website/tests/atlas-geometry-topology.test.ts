import {
  cellToBoundary,
  cellToLatLng,
  cellToVertexes,
  getPentagons,
  gridDisk,
  vertexToLatLng,
} from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  INTERPOLATED_CODE,
  isSupportedCode,
  OBSERVED_CODE,
  PRIOR_DOMINATED_CODE,
  supportName,
  UNKNOWN_CODE,
} from '../src/atlas/geometry/support-codes';
import { buildGridTopology, gridRowOf } from '../src/atlas/geometry/topology';
import { decodedGridFromH3, sortedU64 } from './helpers/atlas-geometry';

const DISK = sortedU64(gridDisk('83754efffffffff', 1));
const PENTAGON = getPentagons(3)[0];
const CLASS_III_DISTORTED = '83006dfffffffff';

describe('shared-grid topology on u32 lanes (fast-load §B.6.4)', () => {
  it('records centres and every corner with dense numeric vertex ids', () => {
    const grid = decodedGridFromH3(DISK);
    const topology = buildGridTopology(grid);
    expect(topology.n).toBe(DISK.length);
    const ids = new Map<string, number>();
    DISK.forEach((cell, row) => {
      expect([topology.centreLat[row], topology.centreLon[row]]).toEqual(
        cellToLatLng(cell),
      );
      const vertexes = cellToVertexes(cell);
      const corners = Array.from(
        topology.cornerIds.subarray(
          topology.cornerOffsets[row],
          topology.cornerOffsets[row + 1],
        ),
      );
      expect(corners).toHaveLength(vertexes.length);
      vertexes.forEach((vertex, corner) => {
        const id = corners[corner];
        if (ids.has(vertex)) expect(id).toBe(ids.get(vertex));
        else ids.set(vertex, id);
        expect([topology.vertexLat[id], topology.vertexLon[id]]).toEqual(
          vertexToLatLng(vertex),
        );
      });
    });
    expect([...ids.values()].sort((a, b) => a - b)).toEqual(
      Array.from({ length: ids.size }, (_, id) => id),
    );
    expect(topology.vertexLat).toHaveLength(ids.size);
  });

  it('shares exactly two corner ids between edge-adjacent cells', () => {
    const topology = buildGridTopology(decodedGridFromH3(DISK));
    const cornersOf = (row: number) =>
      new Set(
        topology.cornerIds.subarray(
          topology.cornerOffsets[row],
          topology.cornerOffsets[row + 1],
        ),
      );
    const centre = DISK.indexOf('83754efffffffff');
    for (let row = 0; row < DISK.length; row += 1) {
      if (row === centre) continue;
      const shared = [...cornersOf(row)].filter((id) =>
        cornersOf(centre).has(id),
      );
      expect(shared).toHaveLength(2);
    }
  });

  it('gives a pentagon five corners', () => {
    const topology = buildGridTopology(decodedGridFromH3([PENTAGON]));
    expect(topology.cornerOffsets[1] - topology.cornerOffsets[0]).toBe(5);
  });

  it('meshes class-III distortion cells by their six vertexes, not their boundary', () => {
    expect(cellToBoundary(CLASS_III_DISTORTED).length).toBeGreaterThan(6);
    const topology = buildGridTopology(
      decodedGridFromH3([CLASS_III_DISTORTED]),
    );
    expect(topology.cornerOffsets[1]).toBe(
      cellToVertexes(CLASS_III_DISTORTED).length,
    );
  });

  it('finds rows by binary search and rejects cells off the grid', () => {
    const grid = decodedGridFromH3(DISK);
    DISK.forEach((cell, row) => expect(gridRowOf(grid, cell)).toBe(row));
    expect(gridRowOf(grid, '83f293fffffffff')).toBeNull();
  });
});

describe('numeric support codes (fast-load §B.3)', () => {
  it('derives the codes from the decoder table', () => {
    expect([
      OBSERVED_CODE,
      INTERPOLATED_CODE,
      PRIOR_DOMINATED_CODE,
      UNKNOWN_CODE,
    ]).toEqual([0, 1, 2, 3]);
    expect([0, 1, 2, 3].map(isSupportedCode)).toEqual([
      true,
      true,
      false,
      false,
    ]);
    expect(supportName(2)).toBe('prior_dominated');
    expect(() => supportName(4)).toThrow('unknown support code 4');
  });
});
