import { cellToBoundary, cellToVertexes, gridDisk } from 'h3-js';
import {
  BufferPolyline,
  Cartesian3,
  Color,
  GeometryInstance,
  GeometryPipeline,
  MaterialAppearance,
  PolygonGeometry,
  PolygonHierarchy,
} from 'cesium';
import { describe, expect, it, vi } from 'vitest';

import type { SurfaceArtifact, SurfaceCell } from '../../src/atlas/contracts';
import { materialForSupport } from '../../src/atlas/scene/support-material';
import { SURFACE_CLEARANCE_METRES } from '../../src/atlas/scene/surface-appearance';
import { heightForCell } from '../../src/atlas/visual-encoding';
import { stubCesiumBrowserImageTypes } from '../helpers/cesium-stubs';
import {
  brighterEdgeColor,
  buildSurfaceLayer,
  edgeColorForSurface,
  h3BoundaryDegrees,
  h3PolygonParts,
} from './surface-layer';
import {
  geometryForExtrudedSurfaceCell,
  geometryForFlatSurfaceCell,
  geometryForSurfaceMesh,
  surfaceMeshForCell,
  surfaceVertexHeights,
  surfaceVertexValues,
} from './surface-mesh';
import {
  paletteBinsForCells,
  partitionSurfaceCells,
  quantizeMetric,
} from './support-material';

const baseCell: SurfaceCell = {
  dist_nearest_obs_km: 25,
  h3_index: '83754efffffffff',
  post_mean: 0.5,
  post_sd: 0.25,
  posterior_contraction: 0.8,
  q025: 0.4,
  q975: 0.6,
  support: 'observed',
};

describe('legacy main-thread builder (parity reference)', () => {
  it('partitions inferred values from unsupported cells', () => {
    const cells: SurfaceCell[] = [
      baseCell,
      { ...baseCell, h3_index: '837541fffffffff', support: 'interpolated' },
      { ...baseCell, h3_index: '837543fffffffff', support: 'unknown' },
      { ...baseCell, h3_index: '837545fffffffff', support: 'prior_dominated' },
    ];
    const artifact = {
      artifact: { metric_domains: { post_mean: [0, 1], post_sd: [0, 1] } },
      cells,
    } as SurfaceArtifact;
    const groups = partitionSurfaceCells(
      artifact.cells,
      'post_mean',
      artifact.artifact.metric_domains.post_mean,
    );

    expect(groups.surface.flatMap((group) => group.cells)).toHaveLength(2);
    expect(groups.support.unknown).toHaveLength(1);
    expect(groups.support.prior_dominated).toHaveLength(1);
  });

  it('uses the selected palette without changing support partitions', () => {
    const groups = partitionSurfaceCells(
      [baseCell],
      'post_mean',
      [0, 1],
      'plasma',
    );
    expect(groups.surface[0].color).toBe('#cc4778');
    expect(groups.support).toEqual({ prior_dominated: [], unknown: [] });
  });

  it('colors prior-dominated texture from the selected surface palette', () => {
    stubCesiumBrowserImageTypes();
    const priorCell = { ...baseCell, support: 'prior_dominated' as const };
    try {
      const [group] = paletteBinsForCells(
        [priorCell],
        'post_mean',
        [0, 1],
        'plasma',
      );
      expect(group.color).toBe('#cc4778');

      const material = materialForSupport('prior_dominated', group.color);
      expect(material.type).toBe('Dot');
      const darkColor = material.uniforms.darkColor as Color;
      const paletteColor = Color.fromCssColorString('#cc4778');
      expect(darkColor.red).toBeCloseTo(paletteColor.red);
      expect(darkColor.green).toBeCloseTo(paletteColor.green);
      expect(darkColor.blue).toBeCloseTo(paletteColor.blue);
      expect(darkColor.alpha).toBeCloseTo(0.46);
      expect((material.uniforms.lightColor as Color).toCssHexString()).not.toBe(
        '#ad8bff',
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('quantizes the full artifact domain into 32 stable bins', () => {
    expect(quantizeMetric(0, [0, 1])).toBe(0);
    expect(quantizeMetric(0.5, [0, 1])).toBe(16);
    expect(quantizeMetric(1, [0, 1])).toBe(31);
    expect(quantizeMetric(2, [0, 1])).toBe(31);
  });

  it('converts H3 latitude-longitude boundaries to Cesium longitude-latitude order', () => {
    const source = cellToBoundary(baseCell.h3_index)[0];
    const converted = h3BoundaryDegrees(baseCell.h3_index)[0];
    expect(converted).toEqual([source[1], source[0]]);
  });

  it('shares averaged heights at triangle vertices between supported neighbors', () => {
    const neighborIndex = gridDisk(baseCell.h3_index, 1).find(
      (index) => index !== baseCell.h3_index,
    );
    expect(neighborIndex).toBeDefined();
    const neighbor = {
      ...baseCell,
      h3_index: neighborIndex!,
      post_mean: 0.9,
      support: 'interpolated',
    } as const;
    const heights = surfaceVertexHeights(
      [baseCell, neighbor],
      [0, 1],
      'post_mean',
    );
    const shared = cellToVertexes(baseCell.h3_index).filter((vertex) =>
      cellToVertexes(neighbor.h3_index).includes(vertex),
    );
    const expected =
      (heightForCell(baseCell, [0, 1], 1) +
        heightForCell(neighbor, [0, 1], 1)) /
      2;

    expect(shared).toHaveLength(2);
    for (const vertex of shared)
      expect(heights.get(vertex)).toBeCloseTo(expected);
  });

  it('does not let unsupported cells influence render-mesh vertices', () => {
    const neighborIndex = gridDisk(baseCell.h3_index, 1).find(
      (index) => index !== baseCell.h3_index,
    );
    expect(neighborIndex).toBeDefined();
    const unknown = {
      ...baseCell,
      h3_index: neighborIndex!,
      post_mean: 1,
      support: 'unknown',
    } as const;
    const heights = surfaceVertexHeights(
      [baseCell, unknown],
      [0, 1],
      'post_mean',
    );

    for (const vertex of cellToVertexes(baseCell.h3_index))
      expect(heights.get(vertex)).toBeCloseTo(
        heightForCell(baseCell, [0, 1], 1),
      );
  });

  it('fans each H3 cell into triangles with a posterior height per vertex', () => {
    const heights = surfaceVertexHeights([baseCell], [0, 1], 'post_mean');
    const mesh = surfaceMeshForCell(baseCell, heights, [0, 1], 'post_mean');

    expect(mesh.vertices).toHaveLength(
      cellToVertexes(baseCell.h3_index).length + 1,
    );
    expect(mesh.indices).toHaveLength((mesh.vertices.length - 1) * 3);
    expect(mesh.vertices[0]).toMatchObject({
      height: heightForCell(baseCell, [0, 1], 1),
      vertexId: null,
    });
    expect(mesh.indices.filter((index) => index === 0)).toHaveLength(
      mesh.vertices.length - 1,
    );
  });

  it('interpolates triangle colors through shared posterior vertices', () => {
    const neighborIndex = gridDisk(baseCell.h3_index, 1).find(
      (index) => index !== baseCell.h3_index,
    )!;
    const neighbor = {
      ...baseCell,
      h3_index: neighborIndex,
      post_mean: 0.9,
    };
    const cells = [baseCell, neighbor];
    const heights = surfaceVertexHeights(cells, [0, 1], 'post_mean');
    const values = surfaceVertexValues(cells, 'post_mean');
    const sharedVertex = cellToVertexes(baseCell.h3_index).find((vertex) =>
      cellToVertexes(neighborIndex).includes(vertex),
    )!;

    expect(values.get(sharedVertex)).toBeCloseTo(0.7);
    const mesh = surfaceMeshForCell(
      baseCell,
      heights,
      [0, 1],
      'post_mean',
      values,
    );
    const geometry = geometryForSurfaceMesh(mesh, 'rainbow', [0, 1]);
    const colors = (
      geometry.attributes as typeof geometry.attributes & {
        surfaceColor: { values: Float32Array };
      }
    ).surfaceColor.values;
    const contourValues = (
      geometry.attributes as typeof geometry.attributes & {
        surfaceValue: { values: Float32Array };
      }
    ).surfaceValue.values;
    const positions = (
      geometry.attributes as typeof geometry.attributes & {
        position: { values: Float64Array };
      }
    ).position.values;
    const renderedCenter = Cartesian3.fromElements(
      positions[0],
      positions[1],
      positions[2],
    );
    const ellipsoidCenter = Cartesian3.fromDegrees(
      mesh.vertices[0].lon,
      mesh.vertices[0].lat,
    );

    expect(colors).toHaveLength(mesh.vertices.length * 3);
    expect(new Set(colors).size).toBeGreaterThan(1);
    expect(contourValues).toHaveLength(mesh.vertices.length);
    expect(contourValues[0]).toBeCloseTo(0.5);
    expect(Cartesian3.distance(renderedCenter, ellipsoidCenter)).toBeCloseTo(
      SURFACE_CLEARANCE_METRES,
      1,
    );
  });

  it('builds extruded cells with a flat posterior top and ground-level sides', () => {
    const geometry = geometryForExtrudedSurfaceCell(
      baseCell,
      [0, 1],
      'post_mean',
    );
    const heights = Array.from(
      (
        geometry.attributes as typeof geometry.attributes & {
          surfaceHeight: { values: Float32Array };
        }
      ).surfaceHeight.values,
    );

    expect(Math.min(...heights)).toBe(0);
    expect(Math.max(...heights)).toBeCloseTo(
      heightForCell(baseCell, [0, 1], 1),
    );
    expect(geometry.indices!.length).toBeGreaterThan(
      cellToVertexes(baseCell.h3_index).length * 3,
    );
  });

  it('keeps extruded antimeridian cell attributes aligned during Cesium splitting', () => {
    const antimeridianCell = {
      ...baseCell,
      h3_index: '84045bbffffffff',
    };
    const instance = new GeometryInstance({
      geometry: geometryForExtrudedSurfaceCell(
        antimeridianCell,
        [0, 1],
        'post_mean',
      ),
    });
    const splitLongitude = (
      GeometryPipeline as unknown as {
        splitLongitude(value: GeometryInstance): void;
      }
    ).splitLongitude;

    expect(() => splitLongitude(instance)).not.toThrow();
  });

  it('builds flat hexagons with one cell height and no side walls', () => {
    const geometry = geometryForFlatSurfaceCell(baseCell, [0, 1], 'post_mean');
    const heights = Array.from(
      (
        geometry.attributes as typeof geometry.attributes & {
          surfaceHeight: { values: Float32Array };
        }
      ).surfaceHeight.values,
    );

    expect(new Set(heights)).toEqual(
      new Set([heightForCell(baseCell, [0, 1], 1)]),
    );
    expect(geometry.indices).toHaveLength(
      cellToVertexes(baseCell.h3_index).length * 3,
    );
  });

  it('tessellates pole-spanning H3 cells into geometry Cesium can project', () => {
    const parts = h3PolygonParts('83f293fffffffff');
    expect(parts.length).toBeGreaterThan(1);
    for (const part of parts) {
      const polygon = new PolygonGeometry({
        closeTop: true,
        height: 0,
        polygonHierarchy: new PolygonHierarchy(
          Cartesian3.fromDegreesArray(part.flat()),
        ),
        vertexFormat: MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat,
      });
      expect(() => PolygonGeometry.createGeometry(polygon)).not.toThrow();
    }
  });

  it('keeps cell edges hidden with the inferred-surface layer', () => {
    stubCesiumBrowserImageTypes();
    const surface = {
      artifact: {
        metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
      },
      cells: [baseCell],
    } as SurfaceArtifact;
    try {
      const layer = buildSurfaceLayer(surface, {
        cellEdges: true,
        edgeColorMode: 'matched',
        edgeFixedColor: '#b9f5ff',
        elevation: false,
        exaggeration: 1,
        geometry: 'triangles',
        metric: 'post_mean',
        mode: 'globe',
        opacity: 0.86,
        palette: 'genome',
      });
      const cellEdges = layer.collection.get(2);

      layer.setVisibility(false, true);
      layer.setCellEdges(true);
      layer.setOpacity(0.8);

      expect(cellEdges.show).toBe(false);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it.each([
    ['matched', '#b9f5ff'],
    ['fixed', '#ff3366'],
  ] as const)(
    'draws visible %s polygon edges',
    async (edgeColorMode, fixedColor) => {
      stubCesiumBrowserImageTypes();
      const surface = {
        artifact: {
          metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
        },
        cells: [baseCell],
      } as SurfaceArtifact;
      try {
        const layer = buildSurfaceLayer(surface, {
          cellEdges: true,
          edgeColorMode,
          edgeFixedColor: fixedColor,
          elevation: false,
          exaggeration: 1,
          geometry: 'triangles',
          metric: 'post_mean',
          mode: 'globe',
          opacity: 0.2,
          palette: 'genome',
        });
        await layer.setCellEdges(true);
        const edges = layer.collection.get(2);
        const surfaceColor = partitionSurfaceCells(
          [baseCell],
          'post_mean',
          [0, 1],
          'genome',
        ).surface[0].color;

        expect(edges.length).toBeGreaterThan(0);
        expect(edges.show).toBe(true);
        expect(
          edgeColorForSurface(surfaceColor, edgeColorMode, fixedColor),
        ).toBe(
          edgeColorMode === 'matched'
            ? brighterEdgeColor(surfaceColor)
            : fixedColor,
        );

        await layer.setCellEdges(false);
        expect(edges.show).toBe(false);
        await layer.setCellEdges(true);
        expect(edges.show).toBe(true);
      } finally {
        vi.unstubAllGlobals();
      }
    },
  );

  it('elevates every edge vertex radially by its mesh height', async () => {
    stubCesiumBrowserImageTypes();
    const surface = {
      artifact: {
        metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
      },
      cells: [baseCell],
    } as SurfaceArtifact;
    try {
      const layer = buildSurfaceLayer(surface, {
        cellEdges: true,
        edgeColorMode: 'matched',
        edgeFixedColor: '#b9f5ff',
        elevation: true,
        exaggeration: 5,
        geometry: 'triangles',
        metric: 'post_mean',
        mode: 'globe',
        opacity: 0.58,
        palette: 'rainbow',
      });
      await layer.setCellEdges(true);
      const edgeCollections = layer.collection.get(2);
      const edgeBuffer = edgeCollections.get(0);
      const edge = new BufferPolyline();
      edgeBuffer.get(0, edge);
      const positions = edge.toJSON().positions as number[];
      const boundary = h3PolygonParts(baseCell.h3_index)[0];
      const radialDistances = [...boundary, boundary[0]].map(
        ([lon, lat], index) => {
          const ground = Cartesian3.fromDegrees(lon, lat);
          const displacement = new Cartesian3(
            positions[index * 3] - ground.x,
            positions[index * 3 + 1] - ground.y,
            positions[index * 3 + 2] - ground.z,
          );
          const normal = Cartesian3.normalize(ground, new Cartesian3());
          return Cartesian3.dot(displacement, normal);
        },
      );

      for (const distance of radialDistances.slice(1))
        expect(distance).toBeCloseTo(radialDistances[0], 2);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('constructs polygon edges when they are enabled after initial render', async () => {
    stubCesiumBrowserImageTypes();
    const surface = {
      artifact: {
        metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
      },
      cells: [baseCell],
    } as SurfaceArtifact;
    try {
      const layer = buildSurfaceLayer(surface, {
        cellEdges: false,
        edgeColorMode: 'matched',
        edgeFixedColor: '#b9f5ff',
        elevation: false,
        exaggeration: 1,
        geometry: 'triangles',
        metric: 'post_mean',
        mode: 'globe',
        opacity: 0.58,
        palette: 'genome',
      });
      const edges = layer.collection.get(2);

      expect(edges.length).toBe(0);
      await layer.setCellEdges(true);

      expect(edges.length).toBeGreaterThan(0);
      expect(edges.show).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
