import { cellToBoundary, gridDisk, isPentagon, latLngToCell } from 'h3-js';
import { describe, expect, it } from 'vitest';

import { observationAnchors } from '../src/atlas/geometry/anchors';
import { vertexMeans } from '../src/atlas/geometry/surface-buffers';
import { gridRowOf } from '../src/atlas/geometry/topology';
import { heightFor } from '../src/atlas/visual-encoding';
import { meshInputFor, sortedU64 } from './helpers/mesh-input';

const HEIGHT_TOLERANCE_METRES = 2 ** (17 - 23);
const CENTRE = latLngToCell(10, 20, 4);
/** The centre row's fan is pulled to half size, so points 88% of the way to
 * the H3 boundary stay in the cell but fall outside every fan triangle. */
const SHRINK = 0.5;
const REACH = 0.88;

describe('observation anchors outside the cell fan (fast-load §B.6.5)', () => {
  it('clamps onto the fan rim and renormalises', () => {
    expect(isPentagon(CENTRE)).toBe(false);
    // Centre at the domain top, neighbours at a quarter: every centre corner
    // touches the centre and two neighbours, so all six rim means are equal
    // and differ from both 0 and the centre height.
    const input = meshInputFor(
      sortedU64(gridDisk(CENTRE, 2)).map((h3) => ({
        h3,
        support: 'observed' as const,
        value: h3 === CENTRE ? 1 : 0.25,
      })),
    );
    const row = gridRowOf(input.grid, CENTRE)!;
    const { topology } = input;
    const corners = topology.cornerIds.subarray(
      topology.cornerOffsets[row],
      topology.cornerOffsets[row + 1],
    );
    const rimHeight = vertexMeans(input).heights[corners[0]];
    for (const id of corners)
      expect(vertexMeans(input).heights[id]).toBe(rimHeight);
    expect(rimHeight).toBeGreaterThan(0);

    const vertexLat = topology.vertexLat.slice();
    const vertexLon = topology.vertexLon.slice();
    const [centreLat, centreLon] = [
      topology.centreLat[row],
      topology.centreLon[row],
    ];
    for (const id of corners) {
      vertexLat[id] = centreLat + (vertexLat[id] - centreLat) * SHRINK;
      vertexLon[id] = centreLon + (vertexLon[id] - centreLon) * SHRINK;
    }
    const shrunk = {
      ...input,
      topology: { ...topology, vertexLat, vertexLon },
    };

    const boundary = cellToBoundary(CENTRE);
    const targets = boundary.flatMap(([lat, lon], index) => {
      const [nextLat, nextLon] = boundary[(index + 1) % boundary.length];
      return [
        [lat, lon],
        [(lat + nextLat) / 2, (lon + nextLon) / 2],
      ];
    });
    const points = Float64Array.from(
      targets.flatMap(([lat, lon]) => [
        centreLon + (lon - centreLon) * REACH,
        centreLat + (lat - centreLat) * REACH,
      ]),
    );
    const anchors = observationAnchors(shrunk, points);
    const centreHeight = heightFor('observed', 1, input.domain, 1);
    expect(Math.abs(centreHeight - rimHeight)).toBeGreaterThan(1_000);

    for (let index = 0; index < targets.length; index += 1) {
      expect(latLngToCell(points[index * 2 + 1], points[index * 2], 4)).toBe(
        CENTRE,
      );
      // Clamped onto the rim: every rim vertex has the same height.
      expect(Math.abs(anchors.heights[index] - rimHeight)).toBeLessThanOrEqual(
        HEIGHT_TOLERANCE_METRES,
      );
      const triangle = anchors.triangles.subarray(index * 9, index * 9 + 9);
      expect([triangle[0], triangle[1], triangle[2]]).toEqual([
        centreLat,
        centreLon,
        centreHeight,
      ]);
      expect([triangle[5], triangle[8]]).toEqual([rimHeight, rimHeight]);
    }
  });
});
