import {
  BufferPolyline,
  Color,
  type BufferPolylineCollection,
  type PrimitiveCollection,
} from 'cesium';
import { describe, expect, it, vi } from 'vitest';

import { planChunks } from '../src/atlas/geometry/chunks';
import {
  brighterEdgeBytes,
  buildEdgeChunk,
  edgeCapacity,
  type EdgeColorSpec,
} from '../src/atlas/geometry/edge-buffers';
import { h3PolygonParts } from '../src/atlas/geometry/polygon-parts';
import type { MeshInput } from '../src/atlas/geometry/surface-buffers';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import {
  brighterEdgeColor,
  buildSurfaceLayer,
  edgeColorForSurface,
} from '../src/atlas/scene/surface-layer';
import { partitionSurfaceCells } from '../src/atlas/scene/support-material';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import { colorAtPosition, type Metric } from '../src/atlas/visual-encoding';
import {
  GOLDEN_DIR,
  PARITY_DIR,
  surfaceFixturesIn,
  type SurfaceFixture,
} from './helpers/atlas-geometry';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';

interface Ring {
  positions: number[];
  color: number[];
}

const FIXED: EdgeColorSpec = { color: '#ff3366', mode: 'fixed' };
const MATCHED: EdgeColorSpec = { mode: 'matched' };

async function legacyRings(
  fixture: SurfaceFixture,
  metric: Metric,
  geometry: SurfaceGeometry,
  edgeColor: EdgeColorSpec,
  factor: number,
): Promise<Map<string, Ring[]>> {
  const fixedColor = edgeColor.mode === 'fixed' ? edgeColor.color : '#b9f5ff';
  const layer = buildSurfaceLayer(
    {
      artifact: fixture.artifact,
      cells: fixture.froundCells,
      schema_version: 1,
    },
    {
      cellEdges: true,
      edgeColorMode: edgeColor.mode,
      edgeFixedColor: fixedColor,
      elevation: factor > 0,
      exaggeration: factor > 0 ? factor : 1,
      geometry,
      metric,
      mode: 'globe',
      opacity: 1,
      palette: 'plasma',
    },
  );
  await layer.setCellEdges(true);
  const buffer = (layer.collection.get(2) as PrimitiveCollection).get(
    0,
  ) as BufferPolylineCollection;
  const partitions = partitionSurfaceCells(
    fixture.froundCells,
    metric,
    fixture.artifact.metric_domains[metric],
    'plasma',
  );
  const rings = new Map<string, Ring[]>();
  const polyline = new BufferPolyline();
  let index = 0;
  for (const group of partitions.surface) {
    const color = Color.fromCssColorString(
      edgeColorForSurface(group.color, edgeColor.mode, fixedColor),
    ).withAlpha(0.92);
    for (const cell of group.cells)
      for (const _ of h3PolygonParts(cell.h3_index)) {
        buffer.get(index, polyline);
        const list = rings.get(cell.h3_index) ?? [];
        list.push({
          color: [color.red, color.green, color.blue, color.alpha],
          positions: polyline.toJSON().positions as number[],
        });
        rings.set(cell.h3_index, list);
        index += 1;
      }
  }
  expect(index).toBe(buffer.primitiveCount);
  return rings;
}

function newRings(
  fixture: SurfaceFixture,
  metric: Metric,
  geometry: SurfaceGeometry,
  edgeColor: EdgeColorSpec,
  factor: number,
): Map<string, Ring[]> {
  const topology = buildGridTopology(fixture.grid);
  const input: MeshInput = {
    domain: fixture.artifact.metric_domains[metric],
    geometry,
    grid: fixture.grid,
    palette: 'plasma',
    support: fixture.support,
    topology,
    values: fixture[metric],
  };
  const rings = new Map<string, Ring[]>();
  const built = planChunks(fixture.grid, topology).chunks.map((chunk) => {
    const edges = buildEdgeChunk(input, chunk, edgeColor, factor);
    let ring = 0;
    for (const row of chunk.rows) {
      const cell = fixture.cells[row];
      if (cell.support !== 'observed' && cell.support !== 'interpolated')
        continue;
      for (const _ of h3PolygonParts(cell.h3_index)) {
        const start = edges.ringOffsets[ring];
        const end = edges.ringOffsets[ring + 1];
        const list = rings.get(cell.h3_index) ?? [];
        list.push({
          color: Array.from(edges.colors.subarray(ring * 4, ring * 4 + 4)),
          positions: Array.from(edges.positions.subarray(start * 3, end * 3)),
        });
        rings.set(cell.h3_index, list);
        ring += 1;
      }
    }
    expect(ring).toBe(edges.ringOffsets.length - 1);
    return edges;
  });
  const capacity = edgeCapacity(built);
  expect(capacity.primitiveCountMax).toBe(
    [...rings.values()].reduce((total, list) => total + list.length, 0),
  );
  expect(capacity.vertexCountMax).toBe(
    [...rings.values()].reduce(
      (total, list) =>
        total + list.reduce((sum, ring) => sum + ring.positions.length / 3, 0),
      0,
    ),
  );
  return rings;
}

const FIXTURES = [
  ...surfaceFixturesIn(GOLDEN_DIR),
  ...surfaceFixturesIn(PARITY_DIR),
];
const CASES = [
  ['triangles', MATCHED, 0, 1e-6],
  ['triangles', FIXED, 5, 0.1],
  ['honmoon', MATCHED, 2.5, 0.1],
  ['hexagons', MATCHED, 5, 1e-6],
  ['extruded', FIXED, 0, 1e-6],
] as const;

describe('edge rings match the legacy edgeDefinitionsForCell (fast-load §B.6.9)', () => {
  describe.each(FIXTURES.map((fixture) => [fixture.name, fixture] as const))(
    '%s',
    (_, fixture) => {
      it.each(CASES)(
        '%s with %o edges at factor %f',
        async (geometry, edgeColor, factor, tolerance) => {
          stubCesiumBrowserImageTypes();
          try {
            for (const metric of ['post_mean', 'post_sd'] as const) {
              const legacy = await legacyRings(
                fixture,
                metric,
                geometry,
                edgeColor,
                factor,
              );
              const ours = newRings(
                fixture,
                metric,
                geometry,
                edgeColor,
                factor,
              );
              expect([...ours.keys()].sort()).toEqual(
                [...legacy.keys()].sort(),
              );
              let worst = 0;
              for (const [h3, rings] of legacy) {
                const mine = ours.get(h3)!;
                expect(mine).toHaveLength(rings.length);
                rings.forEach((ring, index) => {
                  expect(mine[index].positions).toHaveLength(
                    ring.positions.length,
                  );
                  for (
                    let offset = 0;
                    offset < ring.positions.length;
                    offset += 3
                  )
                    worst = Math.max(
                      worst,
                      Math.hypot(
                        ring.positions[offset] - mine[index].positions[offset],
                        ring.positions[offset + 1] -
                          mine[index].positions[offset + 1],
                        ring.positions[offset + 2] -
                          mine[index].positions[offset + 2],
                      ),
                    );
                  ring.color.forEach((channel, axis) =>
                    expect(
                      Math.abs(channel - mine[index].color[axis]),
                    ).toBeLessThanOrEqual(1e-6),
                  );
                });
              }
              expect(
                worst,
                `${metric} worst position error`,
              ).toBeLessThanOrEqual(tolerance);
            }
          } finally {
            vi.unstubAllGlobals();
          }
        },
        60_000,
      );
    },
  );

  it('brightens matched colours exactly like brighterEdgeColor', () => {
    for (let t = 0; t <= 1; t += 0.01) {
      const css = colorAtPosition('rainbow', t);
      const bytes = [1, 3, 5].map((offset) =>
        Number.parseInt(css.slice(offset, offset + 2), 16),
      ) as [number, number, number];
      const expected = brighterEdgeColor(css);
      expect(brighterEdgeBytes(bytes)).toEqual(
        [1, 3, 5].map((offset) =>
          Number.parseInt(expected.slice(offset, offset + 2), 16),
        ),
      );
    }
  });

  it('keeps positions equal to base + normal × base height × factor', () => {
    const [fixture] = surfaceFixturesIn(GOLDEN_DIR);
    const topology = buildGridTopology(fixture.grid);
    const input: MeshInput = {
      domain: fixture.artifact.metric_domains.post_mean,
      geometry: 'triangles',
      grid: fixture.grid,
      palette: 'plasma',
      support: fixture.support,
      topology,
      values: fixture.post_mean,
    };
    const [chunk] = planChunks(fixture.grid, topology).chunks;
    const edges = buildEdgeChunk(input, chunk, MATCHED, 3);
    for (let vertex = 0; vertex < edges.baseHeights.length; vertex += 1)
      for (let axis = 0; axis < 3; axis += 1)
        expect(
          Math.abs(
            edges.positions[vertex * 3 + axis] -
              (edges.basePositions[vertex * 3 + axis] +
                edges.normals[vertex * 3 + axis] *
                  edges.baseHeights[vertex] *
                  3),
          ),
        ).toBeLessThan(0.1);
  });
});
