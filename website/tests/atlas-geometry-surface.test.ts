import {
  cellToChildren,
  cellToLatLng,
  cellToVertexes,
  getBaseCellNumber,
  getRes0Cells,
  gridDisk,
  vertexToLatLng,
} from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  buildSurfaceChunk,
  MAX_ELEVATION_FACTOR,
  paletteBins,
  SURFACE_CLEARANCE_METRES,
  vertexMeans,
  type SurfaceChunkBuffers,
} from '../src/atlas/geometry/surface-buffers';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import { geodeticToEcef } from '../src/atlas/geometry/wgs84';
import {
  colorBytesAtStops,
  heightFor,
  linearStops,
  normalizedValue,
  quantizeMetric,
  type MetricDomain,
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
const RING = DISK.filter((cell) => cell !== CENTRE);
/** Not the identity on [0, 1], so a mean stored unnormalised is visible. */
const DOMAIN: MetricDomain = [0.05, 0.85];

function disk(overrides: Record<string, Partial<TestCell>> = {}): TestCell[] {
  return DISK.map((h3, index) => ({
    h3,
    support: 'interpolated' as const,
    value: 0.1 + index * 0.1,
    ...overrides[h3],
  }));
}

/** The disk with each support state present; the masked cells hold the highest values. */
function maskedDisk(): TestCell[] {
  return disk({
    [RING[0]]: { support: 'unknown', value: 0.8 },
    [RING[2]]: { support: 'prior_dominated', value: 0.75 },
    [RING[4]]: { support: 'observed' },
  });
}

function meshes(cell: TestCell): boolean {
  return cell.support === 'observed' || cell.support === 'interpolated';
}

/**
 * Independent oracle for one H3 vertex: the mean exaggeration-1 height and
 * the normalised mean value of the meshed cells whose `cellToVertexes` list
 * it, summed in float64 in grid order and stored as float32. A vertex with no
 * meshed neighbour is 0.
 */
function cornerMean(
  cells: readonly TestCell[],
  values: Float32Array,
  vertex: string,
  domain: MetricDomain,
): { height: number; value: number } {
  let heightSum = 0;
  let valueSum = 0;
  let count = 0;
  cells.forEach((cell, row) => {
    if (!meshes(cell) || !cellToVertexes(cell.h3).includes(vertex)) return;
    heightSum += heightFor(cell.support, values[row], domain, 1);
    valueSum += values[row];
    count += 1;
  });
  if (count === 0) return { height: 0, value: 0 };
  return {
    height: Math.fround(heightSum / count),
    value: Math.fround(normalizedValue(valueSum / count, domain)),
  };
}

function distance(
  positions: Float64Array,
  vertex: number,
  centre: ArrayLike<number>,
): number {
  return Math.hypot(
    positions[vertex * 3] - centre[0],
    positions[vertex * 3 + 1] - centre[1],
    positions[vertex * 3 + 2] - centre[2],
  );
}

/**
 * Each elevation normal is the geocentric direction of its position, and the
 * chunk sphere holds every vertex at rest and raised by the maximum
 * exaggeration along that normal, as the shader raises it.
 */
function expectBoundsEveryVertex(buffers: SurfaceChunkBuffers): void {
  const { positions, elevationNormals, heights } = buffers;
  const { center, radius } = buffers.boundingSphere;
  expect(heights.length).toBeGreaterThan(0);
  expect(Math.max(...heights)).toBeGreaterThan(0);
  for (let vertex = 0; vertex < heights.length; vertex += 1) {
    const offset = vertex * 3;
    const length = Math.hypot(
      positions[offset],
      positions[offset + 1],
      positions[offset + 2],
    );
    for (let axis = 0; axis < 3; axis += 1)
      expect(
        Math.abs(
          elevationNormals[offset + axis] - positions[offset + axis] / length,
        ),
      ).toBeLessThan(1e-6);
    expect(distance(positions, vertex, center)).toBeLessThanOrEqual(
      radius * (1 + 1e-12),
    );
    const lift = heights[vertex] * MAX_ELEVATION_FACTOR;
    const raised = [0, 1, 2].map(
      (axis) =>
        positions[offset + axis] + elevationNormals[offset + axis] * lift,
    );
    expect(
      Math.hypot(
        raised[0] - center[0],
        raised[1] - center[1],
        raised[2] - center[2],
      ),
    ).toBeLessThanOrEqual(radius * (1 + 1e-12));
  }
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

  it('averages corner heights and values over supported neighbours only', () => {
    const cells = maskedDisk();
    const input = meshInputFor(cells, { domain: DOMAIN });
    const means = vertexMeans(input);
    const { cornerIds, cornerOffsets } = input.topology;
    const ids = new Set<number>();
    cells.forEach((cell, row) => {
      cellToVertexes(cell.h3).forEach((vertex, corner) => {
        const id = cornerIds[cornerOffsets[row] + corner];
        ids.add(id);
        const expected = cornerMean(cells, input.values, vertex, DOMAIN);
        expect(means.heights[id]).toBe(expected.height);
        expect(means.values[id]).toBe(expected.value);
      });
    });
    expect(ids.size).toBe(means.heights.length);
  });

  it('writes each centre and shared corner with its own height, value and colour', () => {
    const cells = maskedDisk();
    const input = meshInputFor(cells, { domain: DOMAIN, palette: 'viridis' });
    const buffers = buildSurfaceChunk(input, wholeGridChunk(input));
    const stops = linearStops('viridis');
    const expectVertex = (
      vertex: number,
      at: {
        height: number;
        value: number;
        t: number;
        lat: number;
        lon: number;
      },
    ) => {
      expect(buffers.heights[vertex]).toBe(at.height);
      expect(buffers.values[vertex]).toBe(at.value);
      expect(
        Array.from(buffers.colors.subarray(vertex * 3, vertex * 3 + 3)),
      ).toEqual(
        colorBytesAtStops(stops, at.t).map((byte) => Math.fround(byte / 255)),
      );
      const expected = new Float64Array(3);
      geodeticToEcef(at.lon, at.lat, SURFACE_CLEARANCE_METRES, expected);
      expect(distance(buffers.positions, vertex, expected)).toBeLessThan(1e-6);
    };
    const vertexOf = new Map<string, number>();
    const expectedIndices: number[] = [];
    let next = 0;
    cells.forEach((cell, row) => {
      if (!meshes(cell)) return;
      const t = normalizedValue(input.values[row], DOMAIN);
      const centre = next++;
      const [centreLat, centreLon] = cellToLatLng(cell.h3);
      expectVertex(centre, {
        height: Math.fround(
          heightFor(cell.support, input.values[row], DOMAIN, 1),
        ),
        lat: centreLat,
        lon: centreLon,
        t,
        value: Math.fround(t),
      });
      const ring = cellToVertexes(cell.h3).map((vertex) => {
        const seen = vertexOf.get(vertex);
        if (seen !== undefined) return seen;
        const index = next++;
        vertexOf.set(vertex, index);
        const mean = cornerMean(cells, input.values, vertex, DOMAIN);
        const [lat, lon] = vertexToLatLng(vertex);
        expectVertex(index, { ...mean, lat, lon, t: mean.value });
        return index;
      });
      ring.forEach((vertex, corner) =>
        expectedIndices.push(centre, vertex, ring[(corner + 1) % ring.length]),
      );
    });
    expect(next).toBe(buffers.heights.length);
    expect(Array.from(buffers.indices)).toEqual(expectedIndices);
  });

  it('memoises vertex means per values array, topology, support and domain', () => {
    const input = meshInputFor(disk());
    const means = vertexMeans(input);
    expect(
      vertexMeans({ ...input, geometry: 'hexagons', palette: 'plasma' }),
    ).toBe(means);
    expect(vertexMeans({ ...input, domain: [0, 2] })).not.toBe(means);
    expect(
      vertexMeans({ ...input, values: Float32Array.from(input.values) }),
    ).not.toBe(means);
    expect(
      vertexMeans({ ...input, topology: buildGridTopology(input.grid) }),
    ).not.toBe(means);
    const remasked = vertexMeans({
      ...input,
      support: meshInputFor(maskedDisk()).support,
    });
    expect(remasked).not.toBe(means);
    expect(Array.from(remasked.heights)).not.toEqual(Array.from(means.heights));
    expect(vertexMeans(input)).toBe(means);
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
    expectBoundsEveryVertex(buildSurfaceChunk(input, wholeGridChunk(input)));
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

  it('takes each bin colour from the first row of its support set in grid order', () => {
    // Every value lies in bin 16 of 32, but each candidate row has its own colour.
    const rows: Pick<TestCell, 'support' | 'value'>[] = [
      { support: 'unknown', value: 0.525 },
      { support: 'interpolated', value: 0.505 }, // first supported row
      { support: 'prior_dominated', value: 0.51 }, // first prior-dominated row
      { support: 'observed', value: 0.515 },
      { support: 'prior_dominated', value: 0.52 }, // last prior-dominated row
      { support: 'interpolated', value: 0.515 },
      { support: 'interpolated', value: 0.53 }, // last supported row
    ];
    const input = meshInputFor(
      DISK.map((h3, row) => ({ h3, ...rows[row] })),
      { geometry: 'hexagons', palette: 'rainbow' },
    );
    const stops = linearStops('rainbow');
    const colourOf = (row: number) =>
      colorBytesAtStops(stops, normalizedValue(input.values[row], [0, 1]));
    const bin = quantizeMetric(input.values[1], [0, 1]);
    expect(
      Array.from(input.values, (value) => quantizeMetric(value, [0, 1])),
    ).toEqual(rows.map(() => bin));
    expect(
      new Set([0, 1, 2, 4, 6].map((row) => colourOf(row).join())).size,
    ).toBe(5);

    const supported = paletteBins(input, 'supported');
    expect(Array.from(supported.binOfRow)).toEqual([
      -1,
      bin,
      -1,
      bin,
      -1,
      bin,
      bin,
    ]);
    expect([...supported.colors]).toEqual([[bin, colourOf(1)]]);

    const prior = paletteBins(input, 'prior_dominated');
    expect(Array.from(prior.binOfRow)).toEqual([-1, -1, bin, -1, bin, -1, -1]);
    expect([...prior.colors]).toEqual([[bin, colourOf(2)]]);
  });

  it('bounds every flat and extruded vertex at rest and fully raised', () => {
    for (const geometry of ['hexagons', 'extruded'] as const) {
      const input = meshInputFor(disk(), { geometry });
      expectBoundsEveryVertex(buildSurfaceChunk(input, wholeGridChunk(input)));
    }
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
