import {
  cellToBoundary,
  cellToLatLng,
  getResolution,
  gridDisk,
  latLngToCell,
} from 'h3-js';
import {
  Cartesian3,
  Cartographic,
  Ellipsoid,
  Math as CesiumMath,
  MaterialAppearance,
  PolygonGeometry,
  PolygonHierarchy,
  type Geometry,
} from 'cesium';
import { describe, expect, it } from 'vitest';

import { planChunks } from '../src/atlas/geometry/chunks';
import { h3PolygonParts } from '../src/atlas/geometry/polygon-parts';
import {
  buildSupportChunk,
  flatCellBuffers,
  type FlatCellBuffers,
} from '../src/atlas/geometry/support-buffers';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import { paletteBinsForCells } from '../src/atlas/scene/support-material';
import { PARITY_DIR, surfaceFixturesIn } from './helpers/atlas-geometry';
import { meshInputFor, sortedU64, wholeGridChunk } from './helpers/mesh-input';

const DISK = sortedU64(gridDisk('83754efffffffff', 1));
const SOUTH_POLE_CELL = '83f293fffffffff';
/** Disks for the PolygonGeometry check. The tangent frame matters away from
 * the equator, and three cells of the 17°S disk cross ±180°. */
const PARITY_SEEDS = [
  '83754efffffffff', // equator (DISK)
  '830883fffffffff', // 60°N
  '83f1b0fffffffff', // 75°S
  '83004bfffffffff', // 85°N
  '839b43fffffffff', // 17°S on ±180°
];
/** Float32 rounding. It rejects the frames this module does not use: the
 * tangent plane at the H3 centre with orthogonal projection is off by 3.9e-6
 * on DISK and 1.6e-4 at 60°N, and plain lon/lat normalisation by 1.0e-4 on
 * DISK and 5.3e-2 at 85°N. */
const ST_TOLERANCE = 1e-6;

function hexBytes(hex: string): [number, number, number] {
  return [1, 3, 5].map((offset) =>
    Number.parseInt(hex.slice(offset, offset + 2), 16),
  ) as [number, number, number];
}

/** The cells a fan-only buffer draws, read back from its fan centres: the
 * first index of each triangle is its fan's centre vertex, at the cell centre. */
function fanCentreCells(
  buffers: FlatCellBuffers | null,
  resolution: number,
): string[] {
  if (!buffers) return [];
  const { indices, positions } = buffers;
  const cells: string[] = [];
  for (let index = 0; index < indices.length; index += 3) {
    const centre = indices[index];
    if (index > 0 && centre === indices[index - 3]) continue;
    const { latitude, longitude } = Cartographic.fromCartesian(
      new Cartesian3(
        positions[centre * 3],
        positions[centre * 3 + 1],
        positions[centre * 3 + 2],
      ),
    );
    cells.push(
      latLngToCell(
        CesiumMath.toDegrees(latitude),
        CesiumMath.toDegrees(longitude),
        resolution,
      ),
    );
  }
  return cells;
}

function cesiumTopFace(h3: string): {
  normals: Float32Array;
  positions: Float64Array;
  st: Float32Array;
} {
  const part = h3PolygonParts(h3)[0];
  const geometry = PolygonGeometry.createGeometry(
    new PolygonGeometry({
      height: 650,
      polygonHierarchy: new PolygonHierarchy(
        Cartesian3.fromDegreesArray(part.flat()),
      ),
      vertexFormat: MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat,
    }),
  ) as Geometry;
  const attributes = geometry.attributes as unknown as {
    normal: { values: Float32Array };
    position: { values: Float64Array };
    st: { values: Float32Array };
  };
  return {
    normals: attributes.normal.values,
    positions: attributes.position.values,
    st: attributes.st.values,
  };
}

describe('support (mask) buffers (fast-load §B.6.5)', () => {
  it('covers exactly the chunk masked cells, unknown and prior-dominated apart', () => {
    const [fixture] = surfaceFixturesIn(PARITY_DIR);
    // Fixture precondition: no cell of the parity subset encloses a pole, so
    // every masked cell is drawn as one fan, one triangle per boundary edge.
    expect(
      fixture.cells
        .filter((cell) => h3PolygonParts(cell.h3_index).length > 1)
        .map((cell) => cell.h3_index),
    ).toEqual([]);
    const resolution = getResolution(fixture.cells[0].h3_index);
    const topology = buildGridTopology(fixture.grid);
    const input = {
      domain: fixture.artifact.metric_domains.post_sd,
      geometry: 'triangles' as const,
      grid: fixture.grid,
      palette: 'plasma' as const,
      support: fixture.support,
      topology,
      values: fixture.post_sd,
    };
    const plan = planChunks(fixture.grid, topology);
    const cellsWith = (rows: Iterable<number>, support: string) =>
      [...rows]
        .filter((row) => fixture.cells[row].support === support)
        .map((row) => fixture.cells[row].h3_index);
    const boundaryEdges = (cells: readonly string[]) =>
      cells.reduce((total, h3) => total + cellToBoundary(h3).length, 0);
    const triangles = (buffers: FlatCellBuffers | null) =>
      buffers ? buffers.indices.length / 3 : 0;
    const drawn = { prior: [] as string[], unknown: [] as string[] };
    for (const chunk of plan.chunks) {
      const support = buildSupportChunk(input, chunk);
      const unknownCells = cellsWith(chunk.rows, 'unknown');
      const priorCells = cellsWith(chunk.rows, 'prior_dominated');
      expect(support.unknown === null).toBe(unknownCells.length === 0);
      const unknownDrawn = fanCentreCells(support.unknown, resolution);
      expect(unknownDrawn).toEqual(unknownCells);
      expect(triangles(support.unknown)).toBe(boundaryEdges(unknownCells));
      const priorDrawn = support.priorDominated.flatMap(({ buffers }) =>
        fanCentreCells(buffers, resolution),
      );
      expect([...priorDrawn].sort()).toEqual([...priorCells].sort());
      expect(
        support.priorDominated.reduce(
          (total, bin) => total + triangles(bin.buffers),
          0,
        ),
      ).toBe(boundaryEdges(priorCells));
      drawn.unknown.push(...unknownDrawn);
      drawn.prior.push(...priorDrawn);
    }
    // Read back from the buffers: across all chunks, every masked cell of the
    // subset is drawn exactly once, in the layer its support selects.
    const allRows = fixture.cells.map((_, row) => row);
    expect(drawn.unknown.sort()).toEqual(cellsWith(allRows, 'unknown').sort());
    expect(drawn.prior.sort()).toEqual(
      cellsWith(allRows, 'prior_dominated').sort(),
    );
  });

  it('bins prior-dominated cells and colours them like paletteBinsForCells', () => {
    const [fixture] = surfaceFixturesIn(PARITY_DIR);
    const topology = buildGridTopology(fixture.grid);
    for (const metric of ['post_mean', 'post_sd'] as const) {
      const domain = fixture.artifact.metric_domains[metric];
      const input = {
        domain,
        geometry: 'triangles' as const,
        grid: fixture.grid,
        palette: 'plasma' as const,
        support: fixture.support,
        topology,
        values: fixture[metric],
      };
      const legacy = paletteBinsForCells(
        fixture.froundCells.filter(
          (cell) => cell.support === 'prior_dominated',
        ),
        metric,
        domain,
        'plasma',
      );
      const support = buildSupportChunk(input, wholeGridChunk(input));
      expect(support.priorDominated.map(({ bin }) => bin)).toEqual(
        legacy.map(({ bin }) => bin),
      );
      support.priorDominated.forEach((entry, index) => {
        expect(entry.color).toEqual(hexBytes(legacy[index].color));
        expect(entry.buffers.indices.length / 3).toBe(
          legacy[index].cells.reduce(
            (total, cell) => total + cellToBoundary(cell.h3_index).length,
            0,
          ),
        );
      });
    }
  });

  it('fans each cell from its centre at the clearance with geodetic normals and st spanning the cell', () => {
    const input = meshInputFor(
      DISK.map((h3) => ({ h3, support: 'unknown' as const, value: 0.2 })),
    );
    const buffers = flatCellBuffers(input, [...wholeGridChunk(input).rows]);
    let vertex = 0;
    for (const h3 of DISK) {
      const [centreLat, centreLon] = cellToLatLng(h3);
      const points = [[centreLat, centreLon], ...cellToBoundary(h3)];
      points.forEach(([lat, lon], index) => {
        const offset = (vertex + index) * 3;
        const expected = Cartesian3.fromDegrees(lon, lat, 650);
        expect(
          Array.from(buffers.positions.subarray(offset, offset + 3)),
        ).toEqual([expected.x, expected.y, expected.z]);
        const normal = Ellipsoid.WGS84.geodeticSurfaceNormal(expected);
        expect(
          Array.from(buffers.normals.subarray(offset, offset + 3)),
        ).toEqual([normal.x, normal.y, normal.z].map(Math.fround));
      });
      const s = points.map((_, index) => buffers.st[(vertex + index) * 2]);
      const t = points.map((_, index) => buffers.st[(vertex + index) * 2 + 1]);
      expect([
        Math.min(...s),
        Math.max(...s),
        Math.min(...t),
        Math.max(...t),
      ]).toEqual([0, 1, 0, 1]);
      vertex += points.length;
    }
    expect(vertex).toBe(buffers.positions.length / 3);
  });

  it('matches Cesium PolygonGeometry st and normals at every boundary vertex, equator to 85°', () => {
    for (const seed of PARITY_SEEDS) {
      const disk = sortedU64(gridDisk(seed, 1));
      const input = meshInputFor(
        disk.map((h3) => ({ h3, support: 'unknown' as const, value: 0.2 })),
      );
      const buffers = flatCellBuffers(input, [...wholeGridChunk(input).rows]);
      let vertex = 0;
      for (const h3 of disk) {
        const reference = cesiumTopFace(h3);
        const count = cellToBoundary(h3).length;
        vertex += 1;
        for (let corner = 0; corner < count; corner += 1, vertex += 1) {
          const ours = buffers.positions.subarray(vertex * 3, vertex * 3 + 3);
          let match = -1;
          for (
            let candidate = 0;
            candidate < reference.positions.length / 3;
            candidate += 1
          )
            if (
              Math.hypot(
                reference.positions[candidate * 3] - ours[0],
                reference.positions[candidate * 3 + 1] - ours[1],
                reference.positions[candidate * 3 + 2] - ours[2],
              ) < 0.01
            )
              match = candidate;
          const label = `${h3} corner ${corner}`;
          expect(match, label).toBeGreaterThanOrEqual(0);
          for (let axis = 0; axis < 2; axis += 1)
            expect(
              Math.abs(
                buffers.st[vertex * 2 + axis] - reference.st[match * 2 + axis],
              ),
              label,
            ).toBeLessThan(ST_TOLERANCE);
          for (let axis = 0; axis < 3; axis += 1)
            expect(
              Math.abs(
                buffers.normals[vertex * 3 + axis] -
                  reference.normals[match * 3 + axis],
              ),
              label,
            ).toBeLessThan(1e-6);
        }
      }
      expect(vertex, seed).toBe(buffers.positions.length / 3);
    }
  });

  it('keeps the legacy fan split for pole-enclosing cells', () => {
    const input = meshInputFor([
      { h3: SOUTH_POLE_CELL, support: 'unknown', value: 0.2 },
    ]);
    const buffers = flatCellBuffers(input, [0]);
    const parts = h3PolygonParts(SOUTH_POLE_CELL);
    expect(parts.length).toBeGreaterThan(1);
    expect(buffers.indices.length / 3).toBe(parts.length);
    expect(buffers.positions.length / 3).toBe(parts.length * 3);
  });
});
