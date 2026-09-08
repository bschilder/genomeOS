import { cellToBoundary, cellToVertexes, gridDisk } from 'h3-js';
import {
  BufferPolyline,
  Cartesian2,
  Cartesian3,
  Color,
  Ellipsoid,
  GeometryInstance,
  GeometryPipeline,
  MaterialAppearance,
  PolygonGeometry,
  PolygonHierarchy,
  PrimitiveCollection,
  VerticalOrigin,
} from 'cesium';
import { describe, expect, it, vi } from 'vitest';

import type {
  ObservationArtifact,
  SurfaceArtifact,
  SurfaceCell,
} from '../src/atlas/contracts';
import type { AtlasHover, AtlasPick } from '../src/atlas/scene/types';
import { cameraState, keyboardCommandFor } from '../src/atlas/scene/camera';
import {
  applyBasemapAppearance,
  availableBasemaps,
  availableTerrains,
  ionCapability,
} from '../src/atlas/scene/context-controller';
import { LayerCache } from '../src/atlas/scene/layer-cache';
import {
  countryLabelDepthTestDistance,
  countryLabelDistanceForScale,
  countryLabelHeight,
  countryLabelText,
} from '../src/atlas/scene/geographic-overlay';
import { highlightStyle } from '../src/atlas/scene/highlight-layer';
import {
  buildObservationLayer,
  observationPickId,
  samplingRingSamples,
} from '../src/atlas/scene/observation-layer';
import {
  atlasHoverForPicks,
  createDragTracker,
  createFrameThrottle,
  createStableHover,
  preferredAtlasPick,
  sameAtlasHover,
  sameAtlasPick,
} from '../src/atlas/scene/picking';
import {
  animateValue,
  waitForReady,
} from '../src/atlas/scene/scene-transition';
import {
  brighterEdgeColor,
  buildSurfaceLayer,
  edgeRendererForMode,
  edgeColorForSurface,
  h3BoundaryDegrees,
  h3PolygonParts,
  surfacePickId,
} from '../src/atlas/scene/surface-layer';
import {
  geometryForSurfaceMesh,
  surfaceMeshForCell,
  surfaceVertexHeights,
  surfaceVertexValues,
  geometryForExtrudedSurfaceCell,
  geometryForFlatSurfaceCell,
  HONMOON_CONTOUR_BANDS,
  honmoonModeForGeometry,
  SURFACE_CLEARANCE_METRES,
} from '../src/atlas/scene/surface-mesh';
import {
  materialForSupport,
  paletteBinsForCells,
  partitionSurfaceCells,
  quantizeMetric,
} from '../src/atlas/scene/support-material';
import {
  applyEarthOpacity,
  resolveElevationView,
  transitionProgress,
} from '../src/atlas/scene/atlas-scene';
import * as atlasScene from '../src/atlas/scene/atlas-scene';
import { styleAtlasScene } from '../src/atlas/scene/scene-policy';
import * as scenePolicy from '../src/atlas/scene/scene-policy';
import { heightForCell } from '../src/atlas/visual-encoding';

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

describe('Earth opacity', () => {
  it('uses an opaque globe by default and enables translucency only below one', () => {
    const globe = {
      depthTestAgainstTerrain: false,
      translucency: {
        backFaceAlpha: 0,
        enabled: true,
        frontFaceAlpha: 0,
      },
    };

    applyEarthOpacity(globe, 1);
    expect(globe.translucency).toMatchObject({
      backFaceAlpha: 1,
      enabled: false,
      frontFaceAlpha: 1,
    });
    expect(globe.depthTestAgainstTerrain).toBe(true);

    applyEarthOpacity(globe, 0.4);
    expect(globe.translucency).toMatchObject({
      backFaceAlpha: 0.4,
      enabled: true,
      frontFaceAlpha: 0.4,
    });
    expect(globe.depthTestAgainstTerrain).toBe(true);
  });
});

function stubCesiumBrowserImageTypes(): void {
  class BrowserImageType {}
  class CanvasImageType extends BrowserImageType {
    height = 0;
    width = 0;
    getContext() {
      return {
        arc: vi.fn(),
        beginPath: vi.fn(),
        bezierCurveTo: vi.fn(),
        closePath: vi.fn(),
        createRadialGradient: () => ({ addColorStop: vi.fn() }),
        ellipse: vi.fn(),
        fill: vi.fn(),
        fillStyle: '',
        lineWidth: 0,
        moveTo: vi.fn(),
        stroke: vi.fn(),
        strokeStyle: '',
      };
    }
  }
  vi.stubGlobal('HTMLCanvasElement', CanvasImageType);
  for (const browserType of [
    'HTMLImageElement',
    'ImageBitmap',
    'OffscreenCanvas',
  ])
    vi.stubGlobal(browserType, BrowserImageType);
  vi.stubGlobal('document', {
    createElement: (name: string) => {
      if (name !== 'canvas') throw new Error(`Unexpected element: ${name}`);
      return new CanvasImageType();
    },
  });
}

function buildObservationLayerForTest(
  shape: 'circle' | 'hemisphere' | 'pin' = 'circle',
) {
  const surface = {
    artifact: {
      metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
      resolution: 3,
    },
    cells: [baseCell],
  } as SurfaceArtifact;
  const observations = {
    artifact: surface.artifact,
    observations: [
      {
        ac: 25,
        an: 100,
        assay: 'genotype',
        citation_text: 'Example publication.',
        cohort_id: 'map-study-1',
        disease_ascertainment_excluded: true,
        ingest_version: 'map-2026-08',
        lat: 5,
        lon: -1,
        population_label: 'Example population',
        radius_km: 12,
        sampling_design: 'population_random',
        source_locator: 'MAP survey 1',
        source_record_id: 'map-surveys:1',
        source_url: 'https://example.org/source',
        study_id: 'map-study-1',
        study_label: 'Example study',
      },
    ],
  } as ObservationArtifact;
  return buildObservationLayer(observations, {
    colorVariable: 'solid',
    elevation: false,
    exaggeration: 1,
    gradient: ['#24144b', '#ad8bff', '#f4c86a'],
    metric: 'post_mean',
    opacity: 0.95,
    samplingAreaColor: '#9af9e2',
    sizeRange: [12, 32],
    samplingAreas: true,
    shape,
    sizeVariable: 'fixed',
    solidColor: '#f4fbff',
    surface,
    surfaceGeometry: 'triangles',
  });
}

describe('Cesium scene policy', () => {
  it('applies a selected ocean color to the globe beneath imagery', () => {
    const globe = { baseColor: Color.BLACK.clone() };
    const policy = scenePolicy as typeof scenePolicy & {
      applyOceanColor?: (target: { baseColor: Color }, color: string) => void;
    };

    policy.applyOceanColor?.(globe, '#225588');

    expect(globe.baseColor.toCssColorString()).toBe('rgb(34,85,136)');
  });

  it('preserves source imagery colors by keeping the global bloom pass off', () => {
    vi.stubGlobal('window', { devicePixelRatio: 1 });
    const viewer = {
      resolutionScale: 0,
      scene: {
        backgroundColor: null,
        fog: { density: 0, enabled: false },
        globe: {
          baseColor: null,
          depthTestAgainstTerrain: false,
          enableLighting: false,
          showGroundAtmosphere: false,
          translucency: {
            backFaceAlpha: 0,
            enabled: true,
            frontFaceAlpha: 0,
          },
        },
        highDynamicRange: false,
        postProcessStages: {
          bloom: {
            enabled: true,
            uniforms: { brightness: 0, contrast: 0 },
          },
          fxaa: { enabled: false },
        },
      },
    };

    styleAtlasScene(viewer as never);

    expect(viewer.scene.postProcessStages.bloom.enabled).toBe(false);
    expect(viewer.scene.postProcessStages.fxaa.enabled).toBe(true);
    expect(viewer.scene.globe.enableLighting).toBe(true);
  });

  it('applies the full zero-to-one basemap appearance range', () => {
    const layer = { alpha: 0.74, brightness: 0.62 };

    applyBasemapAppearance(layer, 1, 0.5);
    expect(layer).toEqual({ alpha: 1, brightness: 0.5 });

    applyBasemapAppearance(layer, 0, 0);
    expect(layer).toEqual({ alpha: 0, brightness: 0 });

    applyBasemapAppearance(layer, -1, 2);
    expect(layer).toEqual({ alpha: 0, brightness: 1 });
  });

  it('keeps recently used render layers and evicts the least recent inactive layer', () => {
    const cache = new LayerCache<object>(2);
    const first = {};
    const second = {};
    const third = {};
    cache.set('first', first);
    cache.set('second', second);
    expect(cache.get('first')).toBe(first);
    cache.set('third', third);

    const evicted: object[] = [];
    cache.prune(first, (layer) => evicted.push(layer));
    expect(cache.get('second')).toBeUndefined();
    expect(cache.get('first')).toBe(first);
    expect(cache.get('third')).toBe(third);
    expect(evicted).toEqual([second]);
  });

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

  it('uses projection-safe cell edges outside the 3D globe', () => {
    expect(edgeRendererForMode('globe')).toBe('buffer');
    expect(edgeRendererForMode('map')).toBe('projected');
    expect(edgeRendererForMode('perspective')).toBe('projected');
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

  it('gates ion-backed context without disabling the public basemap', () => {
    expect(ionCapability('')).toEqual({
      available: false,
      reason: 'Cesium ion access is unavailable in this build.',
    });
    expect(ionCapability('read-only-token')).toEqual({ available: true });
    expect(availableBasemaps('')).toEqual({
      'arcgis-hillshade': true,
      'arcgis-imagery': true,
      'azure-aerial': false,
      'azure-roads': false,
      'aerial-labels': false,
      aerial: false,
      'blue-marble': false,
      'dark-streets': true,
      'earth-at-night': false,
      'esri-ocean': true,
      'google-contour': false,
      'google-roadmap': false,
      'google-satellite': false,
      'google-satellite-labels': false,
      'natural-earth-ii': true,
      openstreetmap: true,
      roads: false,
      'sentinel-2': false,
      'stadia-dark': true,
      'stadia-smooth': true,
      'stadia-toner': true,
      'stadia-watercolor': true,
    });
    expect(Object.values(availableBasemaps('read-only-token'))).not.toContain(
      false,
    );
    expect(availableTerrains('read-only-token')).toEqual({
      'smooth-globe': true,
      'world-terrain': true,
    });
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

  it('maps Honmoon geometries to line-only and filled shader modes', () => {
    expect(HONMOON_CONTOUR_BANDS).toBeGreaterThanOrEqual(32);
    expect(honmoonModeForGeometry('triangles')).toBe(0);
    expect(honmoonModeForGeometry('honmoon')).toBe(1);
    expect(honmoonModeForGeometry('honmoon-fill')).toBe(2);
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

  it('keeps country labels legible and progressively reveals small countries', () => {
    expect(
      countryLabelText({ ADMIN: 'Fallback', NAME_LONG: 'Long name' }),
    ).toBe('Long name');
    expect(countryLabelText({ ADMIN: 'Fallback' })).toBe('Fallback');
    expect(countryLabelDistanceForScale(1.7)).toBeGreaterThan(
      countryLabelDistanceForScale(7),
    );
  });

  it('anchors country labels just above their local elevated surface', () => {
    expect(countryLabelHeight(40_000, 5)).toBe(202_500);
    expect(countryLabelHeight(0, 0)).toBe(2_500);
  });

  it('overlays visible front-side labels without exposing the far hemisphere', () => {
    const depthTestDistance = countryLabelDepthTestDistance(1.7);

    expect(depthTestDistance).toBeGreaterThan(0);
    expect(depthTestDistance).toBeLessThan(Ellipsoid.WGS84.maximumRadius * 2);
    expect(depthTestDistance).toBeLessThanOrEqual(
      countryLabelDistanceForScale(1.7),
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

  it('attaches explicit pick kinds', () => {
    expect(surfacePickId(baseCell)).toEqual({
      h3Index: baseCell.h3_index,
      kind: 'surface',
    });
    expect(observationPickId('map-surveys:1')).toEqual({
      kind: 'observation',
      sourceRecordId: 'map-surveys:1',
    });
  });

  it('controls observation radii independently from measured points', () => {
    stubCesiumBrowserImageTypes();
    try {
      const layer = buildObservationLayerForTest();
      const samplingAreas = layer.collection.get(0);

      layer.setVisibility(false, true);

      expect(samplingAreas.show).toBe(true);
      expect(layer.collection.get(2).show).toBe(false);

      layer.setVisibility(true, false);
      expect(samplingAreas.show).toBe(false);
      expect(layer.collection.get(2).show).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('recolors sampling-area radii without rebuilding observations', () => {
    stubCesiumBrowserImageTypes();
    try {
      const layer = buildObservationLayerForTest();
      const ring = layer.collection.get(0).get(0);

      layer.setSamplingAreaColor('#ff3366');

      const color = ring.material.uniforms.color as Color;
      expect(color.red).toBeCloseTo(1);
      expect(color.green).toBeCloseTo(0.2);
      expect(color.blue).toBeCloseTo(0.4);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it.each([
    ['circle', 2],
    ['hemisphere', 1],
    ['pin', 3],
  ] as const)(
    'depth-tests %s observations and keeps their screen size fixed',
    (shape, index) => {
      stubCesiumBrowserImageTypes();
      try {
        const layer = buildObservationLayerForTest(shape);
        const symbols = layer.collection.get(index);

        const symbol = symbols.get(0);
        expect(symbol.disableDepthTestDistance).toBe(0);
        expect(symbol.scaleByDistance).toBeUndefined();
        if (shape !== 'circle') expect(symbol.sizeInMeters).toBe(false);
      } finally {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
      }
    },
  );

  it.each([
    ['circle', 2],
    ['hemisphere', 1],
    ['pin', 3],
  ] as const)(
    'places %s observations above their sampling rings',
    (shape, index) => {
      stubCesiumBrowserImageTypes();
      try {
        const layer = buildObservationLayerForTest(shape);
        const ringPosition = layer.collection.get(0).get(0).positions[0];
        const symbolPosition = layer.collection.get(index).get(0).position;
        const ringHeight =
          Ellipsoid.WGS84.cartesianToCartographic(ringPosition).height;
        const symbolHeight =
          Ellipsoid.WGS84.cartesianToCartographic(symbolPosition).height;

        expect(symbolHeight - ringHeight).toBeGreaterThanOrEqual(2_500);
      } finally {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
      }
    },
  );

  it('keeps surface-mounted studs screen-upright and opaque above map lines', () => {
    stubCesiumBrowserImageTypes();
    try {
      const circleLayer = buildObservationLayerForTest('circle');
      const hemisphereLayer = buildObservationLayerForTest('hemisphere');
      const circle = circleLayer.collection.get(2).get(0);
      const hemisphere = hemisphereLayer.collection.get(1).get(0);

      expect(hemisphere.width).toBe(circle.pixelSize);
      expect(hemisphere.height).toBeLessThan(hemisphere.width);
      expect(hemisphere.verticalOrigin).toBe(VerticalOrigin.BOTTOM);
      expect(hemisphere.eyeOffset.z).toBeLessThan(0);
      expect(hemisphere.alignedAxis).toEqual(Cartesian3.ZERO);
      hemisphereLayer.setStyleOpacity(1);
      hemisphereLayer.setOpacity(1);
      expect(hemisphere.color.alpha).toBe(1);

      hemisphereLayer.setElevationFactor(4, true);
      expect(hemisphere.alignedAxis).toEqual(Cartesian3.ZERO);
      expect(hemisphere.image).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('raises observations above a replacement surface and keeps highlights last', () => {
    const primitives = new PrimitiveCollection();
    const observations = new PrimitiveCollection();
    const highlights = new PrimitiveCollection();
    const replacementSurface = new PrimitiveCollection();
    primitives.add(observations);
    primitives.add(highlights);
    primitives.add(replacementSurface);
    const scene = atlasScene as typeof atlasScene & {
      raiseScientificOverlays?: (
        target: PrimitiveCollection,
        observationLayer: PrimitiveCollection | null,
        highlightLayer: PrimitiveCollection,
      ) => void;
    };

    scene.raiseScientificOverlays?.(primitives, observations, highlights);

    expect(primitives.get(primitives.length - 2)).toBe(observations);
    expect(primitives.get(primitives.length - 1)).toBe(highlights);
  });

  it('renders pins as fixed-pixel, shaded teardrops anchored at their tip', () => {
    stubCesiumBrowserImageTypes();
    try {
      const pinLayer = buildObservationLayerForTest('pin');
      const pin = pinLayer.collection.get(3).get(0);

      expect(pin.width).toBeGreaterThan(0);
      expect(pin.height).toBeGreaterThan(pin.width);
      expect(pin.sizeInMeters).toBe(false);
      expect(pin.verticalOrigin).toBe(VerticalOrigin.BOTTOM);
      expect(pin.alignedAxis).not.toEqual(Cartesian3.ZERO);
    } finally {
      vi.restoreAllMocks();
      vi.unstubAllGlobals();
    }
  });

  it.each([
    ['circle', 2, 'pixelSize'],
    ['hemisphere', 1, 'width'],
  ] as const)(
    'resizes existing %s primitives without rebuilding the layer',
    (shape, collectionIndex, sizeField) => {
      stubCesiumBrowserImageTypes();
      try {
        const layer = buildObservationLayerForTest(shape);
        const symbols = layer.collection.get(collectionIndex);
        const symbol = symbols.get(0);

        layer.setSizeRange([24, 48]);

        expect(symbols.get(0)).toBe(symbol);
        expect(symbol[sizeField]).toBe(36);
        if (shape === 'hemisphere') expect(symbol.height).toBeLessThan(36);
      } finally {
        vi.unstubAllGlobals();
      }
    },
  );

  it('keeps an elevated sampling radius at one observation height', () => {
    const sourceObservation = {
      ac: 25,
      an: 100,
      assay: 'genotype',
      citation_text: 'Example publication.',
      cohort_id: 'map-study-1',
      disease_ascertainment_excluded: true,
      ingest_version: 'map-2026-08',
      lat: 5,
      lon: -1,
      population_label: 'Example population',
      radius_km: 300,
      sampling_design: 'population_random',
      source_locator: 'MAP survey 1',
      source_record_id: 'map-surveys:1',
      source_url: 'https://example.org/source',
      study_id: 'map-study-1',
      study_label: 'Example study',
    } as ObservationArtifact['observations'][number];
    const sampledPoints: { lat: number; lon: number }[] = [];

    const samples = samplingRingSamples(sourceObservation, (point) => {
      sampledPoints.push({ lat: point.lat, lon: point.lon });
      return sampledPoints.length * 1_000;
    });

    expect(sampledPoints).toEqual([
      { lat: sourceObservation.lat, lon: sourceObservation.lon },
    ]);
    expect(new Set(samples.map((sample) => sample.baseHeight))).toEqual(
      new Set([1_000]),
    );
  });

  it('fades circle outlines with their observation layer', () => {
    stubCesiumBrowserImageTypes();
    try {
      const layer = buildObservationLayerForTest();
      const points = layer.collection.get(2);

      layer.setOpacity(0);

      expect(points.get(0).outlineColor.alpha).toBe(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it.each([
    ['circle', 2],
    ['hemisphere', 1],
    ['pin', 3],
  ] as const)(
    'assigns a new %s color when opacity changes so Cesium uploads it',
    (shape, collectionIndex) => {
      stubCesiumBrowserImageTypes();
      try {
        const layer = buildObservationLayerForTest(shape);
        const symbols = layer.collection.get(collectionIndex) as {
          _propertiesChanged: Uint32Array;
          get(index: number): { color: Color };
        };
        const propertyChangesBefore = [...symbols._propertiesChanged].reduce(
          (total, value) => total + value,
          0,
        );

        layer.setOpacity(0);

        expect(
          [...symbols._propertiesChanged].reduce(
            (total, value) => total + value,
            0,
          ),
        ).toBeGreaterThan(propertyChangesBefore);
        expect(symbols.get(0).color.alpha).toBe(0);
      } finally {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
      }
    },
  );

  it('attenuates measured points and radii with Earth opacity', () => {
    stubCesiumBrowserImageTypes();
    try {
      const layer = buildObservationLayerForTest();
      const ring = layer.collection.get(0).get(0);
      const point = layer.collection.get(2).get(0);

      layer.setEarthOpacity(0.4);

      expect((ring.material.uniforms.color as Color).alpha).toBeCloseTo(
        0.9 * 0.95 * 0.4,
      );
      expect(point.color.alpha).toBeCloseTo(0.97 * 0.95 * 0.4);
      expect(point.outlineColor.alpha).toBeCloseTo(0.92 * 0.95 * 0.4);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('extends the readiness deadline while geometry makes progress', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('window', { setTimeout: globalThis.setTimeout });
    try {
      let postRender = () => {};
      let readyCount = 0;
      const group = {
        collection: { show: true },
        isReady: () => readyCount === 2,
        readyCount: () => readyCount,
      };
      const viewer = {
        scene: {
          postRender: {
            addEventListener(listener: () => void) {
              postRender = listener;
              return () => {};
            },
          },
          requestRender: vi.fn(),
        },
      };
      const outcome = waitForReady(viewer as never, group as never).then(
        () => null,
        (error: Error) => error,
      );

      await vi.advanceTimersByTimeAsync(29_000);
      readyCount = 1;
      postRender();
      await vi.advanceTimersByTimeAsync(29_000);
      readyCount = 2;
      postRender();

      await expect(outcome).resolves.toBeNull();
    } finally {
      vi.unstubAllGlobals();
      vi.useRealTimers();
    }
  });

  it('reports measurable Cesium primitive readiness', async () => {
    let postRender = () => {};
    let readyCount = 0;
    const progress = vi.fn();
    const group = {
      collection: { show: true },
      isReady: () => readyCount === 2,
      readyCount: () => readyCount,
      totalCount: () => 2,
    };
    const viewer = {
      scene: {
        postRender: {
          addEventListener(listener: () => void) {
            postRender = listener;
            return () => {};
          },
        },
        requestRender: vi.fn(),
      },
    };
    const outcome = waitForReady(viewer as never, group as never, progress);

    expect(progress).toHaveBeenLastCalledWith(0);
    readyCount = 1;
    postRender();
    expect(progress).toHaveBeenLastCalledWith(0.5);
    readyCount = 2;
    postRender();

    await outcome;
    expect(progress).toHaveBeenLastCalledWith(1);
  });

  it('hides geometry that stops making readiness progress', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('window', { setTimeout: globalThis.setTimeout });
    try {
      const group = {
        collection: { show: true },
        isReady: () => false,
        readyCount: () => 0,
      };
      const viewer = {
        scene: {
          postRender: {
            addEventListener: () => () => {},
          },
          requestRender: vi.fn(),
        },
      };
      const outcome = waitForReady(viewer as never, group as never).catch(
        (error: Error) => error,
      );

      await vi.advanceTimersByTimeAsync(30_000);

      await expect(outcome).resolves.toMatchObject({
        message: 'Cesium geometry build timed out',
      });
      expect(group.collection.show).toBe(false);
    } finally {
      vi.unstubAllGlobals();
      vi.useRealTimers();
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

  it('distinguishes transient hover from persistent selection', () => {
    expect(highlightStyle('hover')).toEqual({
      color: '#b9f8ff',
      pointSize: 26,
      width: 4,
    });
    expect(highlightStyle('selection')).toEqual({
      color: '#ffd56a',
      pointSize: 32,
      width: 5,
    });
  });

  it('prefers a measured point when it overlaps a modeled cell', () => {
    const surface = { id: surfacePickId(baseCell) };
    const observation = { id: observationPickId('map-surveys:1') };
    expect(preferredAtlasPick([surface, observation])).toEqual(observation.id);
    expect(preferredAtlasPick([surface])).toEqual(surface.id);
    expect(preferredAtlasPick([{ id: 'context' }])).toBeNull();
  });

  it('coalesces hover work to the newest pointer position per frame', () => {
    const frames: FrameRequestCallback[] = [];
    const picked: string[] = [];
    const hover = createFrameThrottle(
      (position: string) => picked.push(position),
      (frame) => {
        frames.push(frame);
        return frames.length;
      },
    );

    hover.queue('first');
    hover.queue('newest');
    expect(frames).toHaveLength(1);
    expect(picked).toEqual([]);
    frames[0](0);
    expect(picked).toEqual(['newest']);

    hover.queue('after');
    hover.cancel();
    frames[1](16);
    expect(picked).toEqual(['newest']);
  });

  it('distinguishes a camera drag from an ordinary click', () => {
    const dragStarts: Cartesian2[] = [];
    const drag = createDragTracker((position) => dragStarts.push(position), 5);

    drag.down(new Cartesian2(20, 20));
    expect(drag.move(new Cartesian2(23, 23))).toBe(false);
    expect(drag.move(new Cartesian2(40, 35))).toBe(true);
    expect(drag.move(new Cartesian2(60, 50))).toBe(true);
    expect(dragStarts).toEqual([new Cartesian2(40, 35)]);

    drag.up();
    expect(drag.move(new Cartesian2(80, 70))).toBe(false);
  });

  it('deduplicates hover picks and tolerates brief misses', () => {
    vi.useFakeTimers();
    try {
      const first = surfacePickId(baseCell);
      const updates: (AtlasPick | null)[] = [];
      const hover = createStableHover(
        (pick) => updates.push(pick),
        sameAtlasPick,
        90,
      );

      hover.update(first);
      hover.update({ ...first });
      hover.update(null);
      vi.advanceTimersByTime(60);
      hover.update(first);
      vi.advanceTimersByTime(60);
      expect(updates).toEqual([first]);

      hover.update(null);
      vi.advanceTimersByTime(90);
      expect(updates).toEqual([first, null]);
      hover.cancel();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps a hover preview stable while the pointer moves within one feature', () => {
    const first: AtlasHover = {
      pick: surfacePickId(baseCell),
      screenPosition: { x: 300, y: 220 },
    };
    const moved: AtlasHover = {
      pick: surfacePickId(baseCell),
      screenPosition: { x: 340, y: 250 },
    };
    expect(sameAtlasHover(first, moved)).toBe(true);
    expect(
      sameAtlasHover(first, {
        pick: observationPickId('map-surveys:1'),
        screenPosition: moved.screenPosition,
      }),
    ).toBe(false);
  });

  it('resolves empty canvas picks as no active hover', () => {
    expect(atlasHoverForPicks([], new Cartesian2(640, 360))).toBeNull();
  });

  it('moves elevation out of 2D while preserving other view choices', () => {
    expect(resolveElevationView('map', true)).toBe('perspective');
    expect(resolveElevationView('map', false)).toBe('map');
    expect(resolveElevationView('globe', true)).toBe('globe');
  });

  it('eases heatmaps continuously between palettes and artifacts', () => {
    expect(transitionProgress(-1)).toBe(0);
    expect(transitionProgress(0)).toBe(0);
    expect(transitionProgress(360)).toBeCloseTo(0.5);
    expect(transitionProgress(720)).toBe(1);
    expect(transitionProgress(1_000)).toBe(1);
  });

  it('interpolates elevation directly without an intermediate fade', async () => {
    const frames: FrameRequestCallback[] = [];
    const values: number[] = [];
    vi.stubGlobal('performance', { now: () => 0 });
    vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => {
      frames.push(frame);
      return frames.length;
    });
    try {
      const viewer = { scene: { requestRender: vi.fn() } };
      const finished = animateValue(viewer as never, 0, 2, false, (value) =>
        values.push(value),
      );

      frames.shift()!(360);
      expect(values.at(-1)).toBeCloseTo(1);
      frames.shift()!(720);
      await finished;
      expect(values).toEqual([1, 2]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('maps focus-scoped keyboard commands and ignores editable targets', () => {
    expect(keyboardCommandFor({ key: '+', target: null })).toBe('zoom-in');
    expect(keyboardCommandFor({ key: 'ArrowLeft', target: null })).toBe(
      'pan-left',
    );
    expect(
      keyboardCommandFor({
        key: 'ArrowLeft',
        target: { tagName: 'INPUT' } as HTMLElement,
      }),
    ).toBeNull();
    expect(keyboardCommandFor({ key: 'x', target: null })).toBeNull();
  });

  it('refuses to serialize Cesium camera values while a scene morph is incomplete', () => {
    const viewer = {
      camera: {
        heading: 0,
        pitch: -Math.PI / 2,
        positionCartographic: {
          height: 1_000_000,
          latitude: undefined,
          longitude: 0,
        },
      },
    };
    expect(cameraState(viewer as never)).toBeNull();
  });

  it('canonicalizes harmless Cesium floating-point noise in shared camera state', () => {
    const viewer = {
      camera: {
        heading: (11.999999999999966 * Math.PI) / 180,
        pitch: (-54.999999999999936 * Math.PI) / 180,
        positionCartographic: {
          height: 4_199_999.999_999_998,
          latitude: (0.999999999999998 * Math.PI) / 180,
          longitude: (9.000000000000005 * Math.PI) / 180,
        },
      },
    };

    expect(cameraState(viewer as never)).toEqual({
      heading: 12,
      height: 4_200_000,
      lat: 1,
      lon: 9,
      pitch: -55,
    });
  });
});
