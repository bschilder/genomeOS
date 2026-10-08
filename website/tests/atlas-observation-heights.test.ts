import { cellToLatLng } from 'h3-js';
import {
  Ellipsoid,
  type PointPrimitiveCollection,
  type PolylineCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ObservationArtifact } from '../src/atlas/contracts';
import {
  buildObservationLayer,
  observationHeightsFromBuffers,
  observationPickId,
} from '../src/atlas/scene/observation-layer';
import {
  anchorsFromBuffers,
  SYMBOL_CLEARANCE_METRES,
} from '../src/atlas/scene/observation-symbols';
import { SURFACE_CLEARANCE_METRES } from '../src/atlas/scene/surface-appearance';
import { columnarHeightSource } from '../src/atlas/scene/surface-heights';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';
import { columnarSurface } from './helpers/columnar-surface';

const KEY = 'fixture-artifact:v3:map-2026-08';
const CELL = '83754efffffffff';
const [LAT, LON] = cellToLatLng(CELL);
const RING_CLEARANCE_METRES = 4_000;

const observations = {
  artifact: {},
  observations: [
    {
      ac: 25,
      an: 100,
      assay: 'genotype',
      citation_text: 'Example publication.',
      cohort_id: 'map-study-1',
      disease_ascertainment_excluded: true,
      ingest_version: 'map-2026-08',
      lat: LAT,
      lon: LON,
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
} as unknown as ObservationArtifact;

function layer() {
  stubCesiumBrowserImageTypes();
  return buildObservationLayer(observations, {
    artifactKey: KEY,
    colorVariable: 'solid',
    elevation: false,
    exaggeration: 1,
    gradient: ['#24144b', '#ad8bff', '#f4c86a'],
    heights: null,
    opacity: 1,
    samplingAreaColor: '#9af9e2',
    samplingAreas: true,
    shape: 'circle',
    sizeRange: [12, 32],
    sizeVariable: 'fixed',
    solidColor: '#f4fbff',
  });
}

function heightOf(
  position: Parameters<typeof Ellipsoid.WGS84.cartesianToCartographic>[0],
) {
  return Ellipsoid.WGS84.cartesianToCartographic(position).height;
}

afterEach(() => vi.unstubAllGlobals());

describe('observation surface heights', () => {
  it('turns worker anchor buffers into anchors, without a triangle when NaN', () => {
    const anchors = anchorsFromBuffers(
      {
        heights: Float64Array.of(1_000, 0),
        triangles: Float64Array.of(
          1,
          2,
          10,
          3,
          4,
          20,
          5,
          6,
          30,
          NaN,
          NaN,
          NaN,
          NaN,
          NaN,
          NaN,
          NaN,
          NaN,
          NaN,
        ),
      },
      2,
    );
    expect(anchors[0]).toEqual({
      height: 1_000,
      triangle: [
        { height: 10, lat: 1, lon: 2 },
        { height: 20, lat: 3, lon: 4 },
        { height: 30, lat: 5, lon: 6 },
      ],
    });
    expect(anchors[1]).toEqual({ height: 0, triangle: null });
  });

  it('refuses anchors that do not match the observations', () => {
    expect(() =>
      anchorsFromBuffers(
        { heights: new Float64Array(1), triangles: new Float64Array(9) },
        2,
      ),
    ).toThrow(/2 observations/);
  });

  it('builds observations first at flat anchors and raises them when heights arrive', () => {
    const group = layer();
    const points = group.collection.get(2) as PointPrimitiveCollection;
    const rings = group.collection.get(0) as PolylineCollection;
    expect(heightOf(points.get(0).position)).toBeCloseTo(
      SURFACE_CLEARANCE_METRES + SYMBOL_CLEARANCE_METRES,
      3,
    );

    group.setSurfaceHeights({
      anchors: [{ height: 1_000, triangle: null }],
      ringBaseHeights: [500],
    });
    group.setElevationFactor(2, true);

    expect(heightOf(points.get(0).position)).toBeCloseTo(
      SURFACE_CLEARANCE_METRES + 2_000 + SYMBOL_CLEARANCE_METRES,
      3,
    );
    expect(heightOf(rings.get(0).positions[0])).toBeCloseTo(
      1_000 + RING_CLEARANCE_METRES,
      3,
    );
  });

  it('keys observation picks and the group by artifact', () => {
    const group = layer();
    const points = group.collection.get(2) as PointPrimitiveCollection;
    expect(points.get(0).id).toEqual(observationPickId('map-surveys:1', KEY));
    expect(observationPickId('map-surveys:1', KEY)).toEqual({
      artifactKey: KEY,
      kind: 'observation',
      sourceRecordId: 'map-surveys:1',
    });
    expect(group.artifactKey).toBe(KEY);
    group.setOpacity(0.25);
    expect(group.opacity()).toBe(0.25);
  });

  it('combines worker anchors with render-tier ring heights', () => {
    const surface = columnarSurface([
      { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'observed' },
    ]);
    const source = columnarHeightSource(surface);
    const heights = observationHeightsFromBuffers(
      {
        heights: Float64Array.of(777),
        triangles: new Float64Array(9).fill(NaN),
      },
      observations.observations,
      source,
      'post_mean',
    );
    expect(heights.anchors).toEqual([{ height: 777, triangle: null }]);
    expect(heights.ringBaseHeights).toEqual([
      source.cellHeight(CELL, 'post_mean'),
    ]);
  });
});
