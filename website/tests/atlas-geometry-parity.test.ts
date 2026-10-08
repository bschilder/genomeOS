import { cellToVertexes, vertexToLatLng } from 'h3-js';
import { Cartesian3, Color, type Geometry } from 'cesium';
import { describe, expect, it } from 'vitest';

import type { SurfaceCell } from '../src/atlas/contracts';
import { planChunks } from '../src/atlas/geometry/chunks';
import {
  buildSurfaceChunk,
  isSmoothGeometry,
  paletteBins,
  type MeshInput,
  type SurfaceChunkBuffers,
} from '../src/atlas/geometry/surface-buffers';
import { isSupportedCode } from '../src/atlas/geometry/support-codes';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import {
  geometryForExtrudedSurfaceCell,
  geometryForFlatSurfaceCell,
  geometryForSurfaceMesh,
  surfaceMeshForCell,
  surfaceVertexHeights,
  surfaceVertexValues,
} from '../src/atlas/scene/surface-mesh';
import { partitionSurfaceCells } from '../src/atlas/scene/support-material';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import type { Metric, PaletteId } from '../src/atlas/visual-encoding';
import {
  GOLDEN_DIR,
  PARITY_DIR,
  surfaceFixturesIn,
  type SurfaceFixture,
} from './helpers/atlas-geometry';

const PALETTES: readonly PaletteId[] = [
  'genome',
  'signal',
  'viridis',
  'cividis',
  'plasma',
  'rainbow',
  'golden',
];
const METRICS: readonly Metric[] = ['post_mean', 'post_sd'];
const GEOMETRIES: readonly SurfaceGeometry[] = [
  'triangles',
  'honmoon',
  'honmoon-fill',
  'hexagons',
  'extruded',
];
const POSITION_TOLERANCE_METRES = 1e-6;
const COLOUR_TOLERANCE = 1 / 255 + 1e-7;
const HDR_GAMMA = 2.2;

interface LegacyCell {
  cell: SurfaceCell;
  geometry: Geometry;
  material: [number, number, number];
}

function attribute(geometry: Geometry, name: string): ArrayLike<number> {
  return (
    geometry.attributes as unknown as Record<
      string,
      { values: ArrayLike<number> }
    >
  )[name].values;
}

/** One float32 unit in the last place at `value`. */
function f32Ulp(value: number): number {
  const magnitude = Math.abs(Math.fround(value));
  if (magnitude === 0) return 2 ** -149;
  return 2 ** (Math.floor(Math.log2(magnitude)) - 23);
}

/** czm_gammaCorrect under HDR for the flat modes; identity otherwise. */
function effectiveDiffuse(
  material: readonly number[],
  vertex: readonly number[],
  gammaOnMaterial: boolean,
  gammaOnVertex: boolean,
): number[] {
  return [0, 1, 2].map(
    (axis) =>
      (gammaOnMaterial ? material[axis] ** HDR_GAMMA : material[axis]) *
      (gammaOnVertex ? vertex[axis] ** HDR_GAMMA : vertex[axis]),
  );
}

function legacyCells(
  fixture: SurfaceFixture,
  metric: Metric,
  palette: PaletteId,
  geometry: SurfaceGeometry,
): LegacyCell[] {
  const domain = fixture.artifact.metric_domains[metric];
  const partitions = partitionSurfaceCells(
    fixture.froundCells,
    metric,
    domain,
    palette,
  );
  const supported = partitions.surface.flatMap(({ cells }) => cells);
  const heights = surfaceVertexHeights(supported, domain, metric);
  const values = surfaceVertexValues(supported, metric);
  const byCell: LegacyCell[] = [];
  for (const group of partitions.surface) {
    const color = Color.fromCssColorString(
      isSmoothGeometry(geometry) ? '#ffffff' : group.color,
    );
    for (const cell of group.cells)
      byCell.push({
        cell,
        geometry:
          geometry === 'extruded'
            ? geometryForExtrudedSurfaceCell(cell, domain, metric)
            : geometry === 'hexagons'
              ? geometryForFlatSurfaceCell(cell, domain, metric)
              : geometryForSurfaceMesh(
                  surfaceMeshForCell(cell, heights, domain, metric, values),
                  palette,
                  domain,
                ),
        material: [color.red, color.green, color.blue],
      });
  }
  const order = new Map(fixture.cells.map((cell, row) => [cell.h3_index, row]));
  return byCell.sort(
    (left, right) =>
      order.get(left.cell.h3_index)! - order.get(right.cell.h3_index)!,
  );
}

function newChunks(
  fixture: SurfaceFixture,
  metric: Metric,
  palette: PaletteId,
  geometry: SurfaceGeometry,
): {
  input: MeshInput;
  chunks: { rows: number[]; buffers: SurfaceChunkBuffers }[];
} {
  const topology = buildGridTopology(fixture.grid);
  const input: MeshInput = {
    domain: fixture.artifact.metric_domains[metric],
    geometry,
    grid: fixture.grid,
    palette,
    support: fixture.support,
    topology,
    values: fixture[metric],
  };
  const plan = planChunks(fixture.grid, topology);
  return {
    chunks: plan.chunks.map((chunk) => ({
      buffers: buildSurfaceChunk(input, chunk),
      rows: [...chunk.rows].filter((row) =>
        isSupportedCode(fixture.support[row]),
      ),
    })),
    input,
  };
}

interface ParityReport {
  maxPositionMetres: number;
  maxHeightUlps: number;
  maxValueUlps: number;
  maxDiffuse: number;
  maxNormal: number;
  failures: string[];
}

function emptyReport(): ParityReport {
  return {
    failures: [],
    maxDiffuse: 0,
    maxHeightUlps: 0,
    maxNormal: 0,
    maxPositionMetres: 0,
    maxValueUlps: 0,
  };
}

function compareVertex(
  report: ParityReport,
  legacy: LegacyCell,
  legacyVertex: number,
  buffers: SurfaceChunkBuffers,
  vertex: number,
  smooth: boolean,
): void {
  const positions = attribute(legacy.geometry, 'position');
  const heights = attribute(legacy.geometry, 'surfaceHeight');
  const values = attribute(legacy.geometry, 'surfaceValue');
  const colors = attribute(legacy.geometry, 'surfaceColor');
  const normals = attribute(legacy.geometry, 'normal');
  const elevationNormals = attribute(legacy.geometry, 'elevationNormal');
  report.maxPositionMetres = Math.max(
    report.maxPositionMetres,
    Math.hypot(
      positions[legacyVertex * 3] - buffers.positions[vertex * 3],
      positions[legacyVertex * 3 + 1] - buffers.positions[vertex * 3 + 1],
      positions[legacyVertex * 3 + 2] - buffers.positions[vertex * 3 + 2],
    ),
  );
  report.maxHeightUlps = Math.max(
    report.maxHeightUlps,
    Math.abs(buffers.heights[vertex] - heights[legacyVertex]) /
      f32Ulp(heights[legacyVertex]),
  );
  report.maxValueUlps = Math.max(
    report.maxValueUlps,
    Math.abs(buffers.values[vertex] - values[legacyVertex]) /
      f32Ulp(values[legacyVertex]),
  );
  const legacyColor = [0, 1, 2].map((axis) => colors[legacyVertex * 3 + axis]);
  const newColor = [0, 1, 2].map((axis) => buffers.colors[vertex * 3 + axis]);
  const before = effectiveDiffuse(legacy.material, legacyColor, !smooth, false);
  const after = effectiveDiffuse([1, 1, 1], newColor, false, !smooth);
  for (let axis = 0; axis < 3; axis += 1) {
    report.maxDiffuse = Math.max(
      report.maxDiffuse,
      Math.abs(before[axis] - after[axis]),
    );
    report.maxNormal = Math.max(
      report.maxNormal,
      Math.abs(
        buffers.normals[vertex * 3 + axis] - normals[legacyVertex * 3 + axis],
      ),
      Math.abs(
        buffers.elevationNormals[vertex * 3 + axis] -
          elevationNormals[legacyVertex * 3 + axis],
      ),
    );
  }
}

/** Legacy smooth vertex identity: the cell centre (index 0) or an H3 vertex id. */
function smoothIdentity(cell: SurfaceCell, legacyVertex: number): string {
  return legacyVertex === 0
    ? `centre:${cell.h3_index}`
    : `vertex:${cellToVertexes(cell.h3_index)[legacyVertex - 1]}`;
}

function checkParity(
  fixture: SurfaceFixture,
  metric: Metric,
  palette: PaletteId,
  geometry: SurfaceGeometry,
): ParityReport {
  const report = emptyReport();
  const smooth = isSmoothGeometry(geometry);
  const legacy = new Map(
    legacyCells(fixture, metric, palette, geometry).map((entry) => [
      entry.cell.h3_index,
      entry,
    ]),
  );
  const { chunks } = newChunks(fixture, metric, palette, geometry);
  let cellsSeen = 0;
  for (const { rows, buffers } of chunks) {
    let vertexCursor = 0;
    let indexCursor = 0;
    const chunkVertex = new Map<string, number>();
    for (const row of rows) {
      const entry = legacy.get(fixture.cells[row].h3_index)!;
      const legacyIndices = Array.from(entry.geometry.indices!);
      const vertexCount = attribute(entry.geometry, 'surfaceHeight').length;
      const local: number[] = [];
      for (
        let legacyVertex = 0;
        legacyVertex < vertexCount;
        legacyVertex += 1
      ) {
        if (!smooth) {
          local.push(vertexCursor++);
          continue;
        }
        const identity = smoothIdentity(entry.cell, legacyVertex);
        let vertex = chunkVertex.get(identity);
        if (vertex === undefined) {
          vertex = vertexCursor++;
          chunkVertex.set(identity, vertex);
        }
        local.push(vertex);
      }
      local.forEach((vertex, legacyVertex) =>
        compareVertex(report, entry, legacyVertex, buffers, vertex, smooth),
      );
      const mapped = legacyIndices.map((index) => local[index]);
      const emitted = buffers.indices.subarray(
        indexCursor,
        indexCursor + mapped.length,
      );
      if (mapped.some((index, offset) => emitted[offset] !== index))
        report.failures.push(
          `${entry.cell.h3_index}: triangle topology differs`,
        );
      indexCursor += mapped.length;
      cellsSeen += 1;
    }
    if (vertexCursor !== buffers.heights.length)
      report.failures.push(`chunk ${buffers.chunk}: vertex count differs`);
    if (indexCursor !== buffers.indices.length)
      report.failures.push(`chunk ${buffers.chunk}: index count differs`);
  }
  if (cellsSeen !== legacy.size)
    report.failures.push(
      `${cellsSeen} cells meshed, legacy meshed ${legacy.size}`,
    );
  return report;
}

const FIXTURES = [
  ...surfaceFixturesIn(GOLDEN_DIR),
  ...surfaceFixturesIn(PARITY_DIR),
];

describe('same-input mesh parity with the legacy builder (fast-load §B.1)', () => {
  it('has the res-3 golden fixtures and the 2,000-cell parity subset', () => {
    expect(surfaceFixturesIn(GOLDEN_DIR).length).toBeGreaterThan(0);
    expect(surfaceFixturesIn(PARITY_DIR).length).toBeGreaterThan(0);
  });

  describe.each(FIXTURES.map((fixture) => [fixture.name, fixture] as const))(
    '%s',
    (_, fixture) => {
      it.each(
        METRICS.flatMap((metric) =>
          GEOMETRIES.map((geometry) => [metric, geometry] as const),
        ),
      )(
        '%s %s matches for all seven palettes',
        (metric, geometry) => {
          for (const palette of PALETTES) {
            const report = checkParity(fixture, metric, palette, geometry);
            const label = `${fixture.name} ${metric} ${geometry} ${palette}`;
            expect(report.failures, label).toEqual([]);
            expect(report.maxPositionMetres, label).toBeLessThanOrEqual(
              POSITION_TOLERANCE_METRES,
            );
            expect(report.maxHeightUlps, label).toBeLessThanOrEqual(1);
            expect(report.maxValueUlps, label).toBeLessThanOrEqual(1);
            expect(report.maxDiffuse, label).toBeLessThanOrEqual(
              COLOUR_TOLERANCE,
            );
            expect(report.maxNormal, label).toBeLessThanOrEqual(1e-6);
          }
        },
        120_000,
      );

      it.each(METRICS)(
        'assigns identical 32-bin membership for %s',
        (metric) => {
          const domain = fixture.artifact.metric_domains[metric];
          const legacy = partitionSurfaceCells(
            fixture.froundCells,
            metric,
            domain,
            'rainbow',
          );
          const bins = paletteBins(
            {
              domain,
              palette: 'rainbow',
              support: fixture.support,
              values: fixture[metric],
            },
            'supported',
          );
          const rowOf = new Map(
            fixture.cells.map((cell, row) => [cell.h3_index, row]),
          );
          for (const group of legacy.surface)
            for (const cell of group.cells)
              expect(bins.binOfRow[rowOf.get(cell.h3_index)!]).toBe(group.bin);
          const newSupported = [...bins.binOfRow].filter(
            (bin) => bin >= 0,
          ).length;
          expect(newSupported).toBe(
            legacy.surface.flatMap(({ cells }) => cells).length,
          );
        },
      );
    },
  );
});

describe('smooth corner vertices sit on the H3 vertex positions', () => {
  it('places every shared corner at vertexToLatLng at the clearance', () => {
    const [fixture] = surfaceFixturesIn(GOLDEN_DIR);
    const { chunks } = newChunks(fixture, 'post_mean', 'rainbow', 'triangles');
    const corners = new Set(
      fixture.cells
        .filter(
          (cell) =>
            cell.support === 'observed' || cell.support === 'interpolated',
        )
        .flatMap((cell) => cellToVertexes(cell.h3_index)),
    );
    const expected = [...corners].map((vertex) => {
      const [lat, lon] = vertexToLatLng(vertex);
      return Cartesian3.fromDegrees(lon, lat, 650);
    });
    const emitted = chunks.flatMap(({ buffers }) =>
      Array.from({ length: buffers.heights.length }, (_, vertex) =>
        Cartesian3.fromArray(Array.from(buffers.positions), vertex * 3),
      ),
    );
    for (const position of expected)
      expect(
        emitted.some(
          (candidate) => Cartesian3.distance(candidate, position) < 1e-6,
        ),
      ).toBe(true);
  });
});
