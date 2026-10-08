import {
  cellToBoundary,
  cellToLatLng,
  cellToVertexes,
  gridDisk,
  vertexToLatLng,
} from 'h3-js';
import { describe, expect, it } from 'vitest';

import { resolveSurfaceRow } from '../src/atlas/geometry/pick-resolver';
import {
  buildSurfaceChunk,
  SURFACE_CLEARANCE_METRES,
  type MeshInput,
  type SurfaceChunkBuffers,
} from '../src/atlas/geometry/surface-buffers';
import { geodeticToEcef } from '../src/atlas/geometry/wgs84';
import type { SurfaceArtifact } from '../src/atlas/surface-columns';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import { heightFor } from '../src/atlas/visual-encoding';
import { meshInputFor, sortedU64, wholeGridChunk } from './helpers/mesh-input';

const CENTRE = '83754efffffffff';
const DISK = sortedU64(gridDisk(CENTRE, 1));
const TALL = 0.9;
const SHORT = 0.2;

function setup(geometry: SurfaceGeometry): {
  input: MeshInput;
  surface: SurfaceArtifact;
  buffers: SurfaceChunkBuffers;
  heights: (row: number) => number;
} {
  const input = meshInputFor(
    DISK.map((h3) => ({
      h3,
      support: 'interpolated' as const,
      value: h3 === CENTRE ? TALL : SHORT,
    })),
    { geometry },
  );
  const surface = {
    artifact: {
      metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
      resolution: 3,
    },
    artifactKey: 'fixture:v1:d1',
    detail: null,
    grid: input.grid,
    support: input.support,
    values: { post_mean: input.values, post_sd: input.values },
  } as unknown as SurfaceArtifact;
  return {
    buffers: buildSurfaceChunk(input, wholeGridChunk(input)),
    heights: (row) => heightFor('interpolated', input.values[row], [0, 1], 1),
    input,
    surface,
  };
}

function displaced(
  buffers: SurfaceChunkBuffers,
  vertex: number,
  factor: number,
): number[] {
  return [0, 1, 2].map(
    (axis) =>
      buffers.positions[vertex * 3 + axis] +
      buffers.elevationNormals[vertex * 3 + axis] *
        buffers.heights[vertex] *
        factor,
  );
}

function blend(
  points: readonly number[][],
  weights: readonly number[],
): [number, number, number] {
  return [0, 1, 2].map((axis) =>
    points.reduce(
      (total, point, index) => total + point[axis] * weights[index],
      0,
    ),
  ) as [number, number, number];
}

describe('surface pick resolution (fast-load §B.6.6)', () => {
  it('reads the ellipsoid hit at elevation factor 0', () => {
    const { surface, heights } = setup('triangles');
    DISK.forEach((h3, row) => {
      const [lat, lon] = cellToLatLng(h3);
      const pick = (hit: { lat: number; lon: number } | null) =>
        resolveSurfaceRow(
          {
            cartesian: null,
            clearance: SURFACE_CLEARANCE_METRES,
            ellipsoidHit: hit,
            factor: 0,
            geometry: 'triangles',
          },
          surface,
          heights,
        );
      expect(pick({ lat, lon })).toBe(row);
      for (const [vertexLat, vertexLon] of cellToBoundary(h3))
        expect(
          pick({
            lat: lat + (vertexLat - lat) * 0.99,
            lon: lon + (vertexLon - lon) * 0.99,
          }),
        ).toBe(row);
      expect(pick(null)).toBeNull();
    });
    expect(
      resolveSurfaceRow(
        {
          cartesian: null,
          clearance: SURFACE_CLEARANCE_METRES,
          ellipsoidHit: { lat: -60, lon: -30 },
          factor: 0,
          geometry: 'triangles',
        },
        surface,
        heights,
      ),
    ).toBeNull();
  });

  it.each(['triangles', 'honmoon', 'hexagons'] as const)(
    'undoes the radial lift near cell edges at exaggeration 5 (%s)',
    (geometry) => {
      const { surface, buffers, heights, input } = setup(geometry);
      let triangle = 0;
      DISK.forEach((h3, row) => {
        const corners =
          input.topology.cornerOffsets[row + 1] -
          input.topology.cornerOffsets[row];
        for (let corner = 0; corner < corners; corner += 1, triangle += 1) {
          const vertices = [0, 1, 2].map((offset) =>
            displaced(buffers, buffers.indices[triangle * 3 + offset], 5),
          );
          for (const weights of [
            [0.02, 0.49, 0.49],
            [0.02, 0.9, 0.08],
            [0.34, 0.33, 0.33],
          ])
            expect(
              resolveSurfaceRow(
                {
                  cartesian: blend(vertices, weights),
                  clearance: SURFACE_CLEARANCE_METRES,
                  ellipsoidHit: null,
                  factor: 5,
                  geometry,
                },
                surface,
                heights,
              ),
              `${h3} triangle ${corner} ${weights}`,
            ).toBe(row);
        }
      });
    },
  );

  it.each([1, 5])(
    'gives extruded wall hits to the taller cell at exaggeration %d',
    (factor) => {
      const { surface, buffers, heights, input } = setup('extruded');
      const centreRow = DISK.indexOf(CENTRE);
      const { cornerOffsets } = input.topology;
      let base = 0;
      for (let row = 0; row < centreRow; row += 1) {
        const count = cornerOffsets[row + 1] - cornerOffsets[row];
        base += 1 + count * 5;
      }
      const corners = cellToVertexes(CENTRE);
      const resolve = (cartesian: [number, number, number]) =>
        resolveSurfaceRow(
          {
            cartesian,
            clearance: SURFACE_CLEARANCE_METRES,
            ellipsoidHit: null,
            factor,
            geometry: 'extruded',
          },
          surface,
          heights,
        );
      let walls = 0;
      for (const neighbour of DISK.filter((cell) => cell !== CENTRE)) {
        const neighbourRow = DISK.indexOf(neighbour);
        const shared = cellToVertexes(neighbour);
        const corner = corners.findIndex(
          (vertex, index) =>
            shared.includes(vertex) &&
            shared.includes(corners[(index + 1) % corners.length]),
        );
        expect(corner, neighbour).toBeGreaterThanOrEqual(0);
        const wall = base + 1 + corners.length + corner * 4;
        const [bottomFirst, bottomSecond, topFirst, topSecond] = [
          0, 1, 2, 3,
        ].map((offset) => displaced(buffers, wall + offset, factor));
        const shortTop = heights(neighbourRow) * factor;
        const tallTop = heights(centreRow) * factor;
        for (const along of [0.3, 0.5, 0.7])
          for (const up of [0.25, 0.5, 0.9]) {
            const altitude = shortTop + 10 + (tallTop - shortTop - 20) * up;
            const fraction = altitude / (tallTop + 1);
            const point = blend(
              [bottomFirst, bottomSecond, topFirst, topSecond],
              [
                (1 - along) * (1 - fraction),
                along * (1 - fraction),
                (1 - along) * fraction,
                along * fraction,
              ],
            );
            expect(resolve(point), `${neighbour} wall ${along} ${up}`).toBe(
              centreRow,
            );
          }
        const [lat, lon] = cellToLatLng(neighbour);
        const [vertexLat, vertexLon] = vertexToLatLng(corners[corner]);
        const nearEdge = [0, 0, 0];
        geodeticToEcef(
          lon + (vertexLon - lon) * 0.97,
          lat + (vertexLat - lat) * 0.97,
          SURFACE_CLEARANCE_METRES + 1 + shortTop,
          nearEdge,
        );
        expect(
          resolve(nearEdge as [number, number, number]),
          `${neighbour} top`,
        ).toBe(neighbourRow);
        walls += 1;
      }
      expect(walls).toBe(6);
    },
  );
});
