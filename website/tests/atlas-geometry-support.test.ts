import { cellToBoundary, cellToLatLng, gridDisk } from 'h3-js';
import {
  Cartesian3,
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

function hexBytes(hex: string): [number, number, number] {
  return [1, 3, 5].map((offset) =>
    Number.parseInt(hex.slice(offset, offset + 2), 16),
  ) as [number, number, number];
}

function cesiumSt(h3: string): { positions: Float64Array; st: Float32Array } {
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
    position: { values: Float64Array };
    st: { values: Float32Array };
  };
  return { positions: attributes.position.values, st: attributes.st.values };
}

describe('support (mask) buffers (fast-load §B.6.5)', () => {
  it('covers exactly the chunk masked cells, unknown and prior-dominated apart', () => {
    const [fixture] = surfaceFixturesIn(PARITY_DIR);
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
    const counted = { prior: 0, unknown: 0 };
    for (const chunk of plan.chunks) {
      const support = buildSupportChunk(input, chunk);
      const unknownRows = [...chunk.rows].filter(
        (row) => fixture.cells[row].support === 'unknown',
      );
      const priorRows = [...chunk.rows].filter(
        (row) => fixture.cells[row].support === 'prior_dominated',
      );
      const expectedUnknown = unknownRows.reduce(
        (total, row) =>
          total + h3PolygonParts(fixture.cells[row].h3_index).length,
        0,
      );
      const triangles = (buffers: FlatCellBuffers | null) =>
        buffers ? buffers.indices.length / 3 : 0;
      expect(support.unknown === null).toBe(unknownRows.length === 0);
      expect(triangles(support.unknown)).toBe(
        unknownRows.reduce(
          (total, row) =>
            total + cellToBoundary(fixture.cells[row].h3_index).length,
          0,
        ),
      );
      expect(expectedUnknown).toBe(unknownRows.length);
      const priorTriangles = support.priorDominated.reduce(
        (total, bin) => total + triangles(bin.buffers),
        0,
      );
      expect(priorTriangles).toBe(
        priorRows.reduce(
          (total, row) =>
            total + cellToBoundary(fixture.cells[row].h3_index).length,
          0,
        ),
      );
      counted.unknown += unknownRows.length;
      counted.prior += priorRows.length;
    }
    expect(counted.unknown).toBe(
      fixture.cells.filter((cell) => cell.support === 'unknown').length,
    );
    expect(counted.prior).toBe(
      fixture.cells.filter((cell) => cell.support === 'prior_dominated').length,
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

  it('fans each cell from its centre at the clearance with st spanning the cell', () => {
    const input = meshInputFor(
      DISK.map((h3) => ({ h3, support: 'unknown' as const, value: 0.2 })),
    );
    const buffers = flatCellBuffers(input, [...wholeGridChunk(input).rows]);
    let vertex = 0;
    for (const h3 of DISK) {
      const [centreLat, centreLon] = cellToLatLng(h3);
      const points = [[centreLat, centreLon], ...cellToBoundary(h3)];
      points.forEach(([lat, lon], index) => {
        const expected = Cartesian3.fromDegrees(lon, lat, 650);
        expect(
          Array.from(
            buffers.positions.subarray(
              (vertex + index) * 3,
              (vertex + index) * 3 + 3,
            ),
          ),
        ).toEqual([expected.x, expected.y, expected.z]);
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

  it('matches Cesium PolygonGeometry st at every boundary vertex', () => {
    const input = meshInputFor(
      DISK.map((h3) => ({ h3, support: 'unknown' as const, value: 0.2 })),
    );
    const buffers = flatCellBuffers(input, [...wholeGridChunk(input).rows]);
    let vertex = 0;
    for (const h3 of DISK) {
      const reference = cesiumSt(h3);
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
        expect(match, `${h3} corner ${corner}`).toBeGreaterThanOrEqual(0);

        expect(
          Math.abs(buffers.st[vertex * 2] - reference.st[match * 2]),
        ).toBeLessThan(1e-4);
        expect(
          Math.abs(buffers.st[vertex * 2 + 1] - reference.st[match * 2 + 1]),
        ).toBeLessThan(1e-4);
      }
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
