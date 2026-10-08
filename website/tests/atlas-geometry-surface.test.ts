import {
  cellToChildren,
  cellToVertexes,
  getBaseCellNumber,
  getRes0Cells,
  gridDisk,
} from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  buildSurfaceChunk,
  MAX_ELEVATION_FACTOR,
  paletteBins,
  vertexMeans,
} from '../src/atlas/geometry/surface-buffers';
import {
  colorBytesAtStops,
  heightFor,
  linearStops,
  normalizedValue,
} from '../src/atlas/visual-encoding';
import {
  maxIndex,
  meshInputFor,
  sortedU64,
  wholeGridChunk,
  type TestCell,
} from './helpers/mesh-input';

const CENTRE = '83754efffffffff';
const DISK = sortedU64(gridDisk(CENTRE, 1));

function disk(overrides: Record<string, Partial<TestCell>> = {}): TestCell[] {
  return DISK.map((h3, index) => ({
    h3,
    support: 'interpolated' as const,
    value: 0.1 + index * 0.1,
    ...overrides[h3],
  }));
}

function distance(
  positions: Float64Array,
  vertex: number,
  centre: readonly number[],
): number {
  return Math.hypot(
    positions[vertex * 3] - centre[0],
    positions[vertex * 3 + 1] - centre[1],
    positions[vertex * 3 + 2] - centre[2],
  );
}

describe('smooth surface chunks (fast-load §B.6.5)', () => {
  it('shares one vertex per H3 corner and fans each supported cell', () => {
    const input = meshInputFor(disk());
    const buffers = buildSurfaceChunk(input, wholeGridChunk(input));
    const corners = new Set(DISK.flatMap((cell) => cellToVertexes(cell)));
    expect(buffers.heights).toHaveLength(DISK.length + corners.size);
    expect(buffers.indices).toBeInstanceOf(Uint16Array);
    expect(buffers.indices).toHaveLength(
      DISK.reduce((total, cell) => total + cellToVertexes(cell).length * 3, 0),
    );
    expect(buffers.normals).toBe(buffers.elevationNormals);
  });

  it('averages corner heights over supported neighbours only', () => {
    const neighbour = DISK.find((cell) => cell !== CENTRE)!;
    const input = meshInputFor(
      disk({ [neighbour]: { support: 'unknown', value: 1 } }),
    );
    const means = vertexMeans(input);
    const row = DISK.indexOf(CENTRE);
    const { cornerIds, cornerOffsets } = input.topology;
    cellToVertexes(CENTRE).forEach((vertex, corner) => {
      const id = cornerIds[cornerOffsets[row] + corner];
      const contributors = DISK.flatMap((cell, index) =>
        cell !== neighbour && cellToVertexes(cell).includes(vertex)
          ? [index]
          : [],
      );
      const expected =
        contributors.reduce(
          (total, index) =>
            total + heightFor('interpolated', input.values[index], [0, 1], 1),
          0,
        ) / contributors.length;
      expect(means.heights[id]).toBe(Math.fround(expected));
    });
  });

  it('memoises vertex means per values array, topology and domain', () => {
    const input = meshInputFor(disk());
    expect(vertexMeans(input)).toBe(
      vertexMeans({ ...input, palette: 'plasma' }),
    );
    expect(vertexMeans({ ...input, domain: [0, 2] })).not.toBe(
      vertexMeans(input),
    );
  });

  it('colours vertices from the palette exactly as a fresh build would after a recolour', () => {
    const input = meshInputFor(disk());
    buildSurfaceChunk(input, wholeGridChunk(input));
    const recoloured = buildSurfaceChunk(
      { ...input, palette: 'viridis' },
      wholeGridChunk(input),
    );
    const fresh = buildSurfaceChunk(
      meshInputFor(disk(), { palette: 'viridis' }),
      wholeGridChunk(input),
    );
    expect(Array.from(recoloured.colors)).toEqual(Array.from(fresh.colors));
    const stops = linearStops('viridis');
    const row = 0;
    expect(Array.from(recoloured.colors.subarray(0, 3))).toEqual(
      colorBytesAtStops(stops, normalizedValue(input.values[row], [0, 1])).map(
        (byte) => Math.fround(byte / 255),
      ),
    );
  });

  it('bounds every vertex at rest and fully raised', () => {
    const input = meshInputFor(disk());
    const buffers = buildSurfaceChunk(input, wholeGridChunk(input));
    const { center, radius } = buffers.boundingSphere;
    for (let vertex = 0; vertex < buffers.heights.length; vertex += 1) {
      expect(distance(buffers.positions, vertex, center)).toBeLessThanOrEqual(
        radius * (1 + 1e-12),
      );
      const lift = buffers.heights[vertex] * MAX_ELEVATION_FACTOR;
      const raised = [0, 1, 2].map(
        (axis) =>
          buffers.positions[vertex * 3 + axis] +
          buffers.elevationNormals[vertex * 3 + axis] * lift,
      );
      expect(
        Math.hypot(
          raised[0] - center[0],
          raised[1] - center[1],
          raised[2] - center[2],
        ),
      ).toBeLessThanOrEqual(radius * (1 + 1e-12));
    }
  });

  it('returns empty buffers for a chunk with no supported cells', () => {
    const input = meshInputFor(
      DISK.map((h3) => ({ h3, support: 'unknown' as const, value: 0.5 })),
    );
    const buffers = buildSurfaceChunk(input, wholeGridChunk(input));
    expect(buffers.positions).toHaveLength(0);
    expect(buffers.indices).toHaveLength(0);
    expect(buffers.boundingSphere.radius).toBe(0);
  });
});

describe('hexagon and extruded surface chunks (fast-load §B.6.5)', () => {
  it('gives flat hexagons one height per cell, no walls and the bin colour', () => {
    const input = meshInputFor(disk(), {
      geometry: 'hexagons',
      palette: 'plasma',
    });
    const buffers = buildSurfaceChunk(input, wholeGridChunk(input));
    const bins = paletteBins(input, 'supported');
    let vertex = 0;
    DISK.forEach((cell, row) => {
      const count = cellToVertexes(cell).length + 1;
      const color = bins.colors.get(bins.binOfRow[row])!;
      for (let index = 0; index < count; index += 1, vertex += 1) {
        expect(buffers.heights[vertex]).toBe(
          Math.fround(heightFor('interpolated', input.values[row], [0, 1], 1)),
        );
        expect(
          Array.from(buffers.colors.subarray(vertex * 3, vertex * 3 + 3)),
        ).toEqual(color.map((byte) => Math.fround(byte / 255)));
      }
    });
    expect(vertex).toBe(buffers.heights.length);
  });

  it('takes each bin colour from its first supported row in grid order', () => {
    const cells = disk().map((cell) => ({ ...cell, value: 0.5 }));
    cells[3] = { ...cells[3], value: 0.505 };
    const input = meshInputFor(cells, {
      geometry: 'hexagons',
      palette: 'rainbow',
    });
    const bins = paletteBins(input, 'supported');
    expect(new Set(bins.binOfRow).size).toBe(1);
    expect(bins.colors.get(bins.binOfRow[0])).toEqual(
      colorBytesAtStops(
        linearStops('rainbow'),
        normalizedValue(Math.fround(0.5), [0, 1]),
      ),
    );
  });

  it('extrudes walls to the ground and the top to the cell height', () => {
    const input = meshInputFor(disk(), { geometry: 'extruded' });
    const buffers = buildSurfaceChunk(input, wholeGridChunk(input));
    expect(Math.min(...buffers.heights)).toBe(0);
    expect(Math.max(...buffers.heights)).toBe(
      Math.fround(
        Math.max(
          ...DISK.map((_, index) =>
            heightFor('interpolated', input.values[index], [0, 1], 1),
          ),
        ),
      ),
    );
    expect(buffers.normals).not.toBe(buffers.elevationNormals);
  });

  it('switches to 32-bit indices once a chunk exceeds 65,535 vertices', () => {
    const [base] = getRes0Cells().filter(
      (cell) => getBaseCellNumber(cell) === 20,
    );
    const cells = sortedU64(cellToChildren(base, 4)).map((h3) => ({
      h3,
      support: 'observed' as const,
      value: 0.4,
    }));
    const extrudedInput = meshInputFor(cells, { geometry: 'extruded' });
    const extruded = buildSurfaceChunk(
      extrudedInput,
      wholeGridChunk(extrudedInput),
    );
    expect(extruded.heights.length).toBeGreaterThan(65_535);
    expect(extruded.indices).toBeInstanceOf(Uint32Array);
    expect(maxIndex(extruded.indices)).toBe(extruded.heights.length - 1);
    const smoothInput = meshInputFor(cells, { geometry: 'triangles' });
    const smooth = buildSurfaceChunk(smoothInput, wholeGridChunk(smoothInput));
    expect(smooth.heights.length).toBeLessThanOrEqual(65_535);
    expect(smooth.indices).toBeInstanceOf(Uint16Array);
  });
});
