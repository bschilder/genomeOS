import { cellToLatLng } from 'h3-js';
import {
  Ellipsoid,
  type PointPrimitiveCollection,
  type PolylineCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ObservationArtifact } from '../src/atlas/contracts';
import { HighlightLayer } from '../src/atlas/scene/highlight-layer';
import { columnarHeightSource } from '../src/atlas/scene/surface-heights';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';
import { columnarSurface } from './helpers/columnar-surface';

const CELL = '83754efffffffff';
const HIGHLIGHT_CLEARANCE_METRES = 5_500;

function setup() {
  stubCesiumBrowserImageTypes();
  const surface = columnarSurface([
    { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'observed' },
  ]);
  const source = columnarHeightSource(surface);
  const [lat, lon] = cellToLatLng(CELL);
  const observations = {
    observations: [{ lat, lon, source_record_id: 'map-surveys:1' }],
  } as unknown as ObservationArtifact;
  const layer = new HighlightLayer({ requestRender: vi.fn() } as never);
  layer.setArtifacts(source, observations, 'post_mean', true, 2);
  const lines = layer.collection.get(0) as PolylineCollection;
  const points = layer.collection.get(1) as PointPrimitiveCollection;
  return { layer, lines, observations, points, source, surface };
}

afterEach(() => vi.unstubAllGlobals());

describe('selection highlight from the render tier', () => {
  it('outlines a selected cell at its render-tier top', () => {
    const { layer, lines, source, surface } = setup();
    layer.setSelection({
      artifactKey: surface.artifactKey,
      h3Index: CELL,
      kind: 'surface',
      row: 0,
    });

    const selection = lines.get(1);
    expect(selection.show).toBe(true);
    expect(
      Ellipsoid.WGS84.cartesianToCartographic(selection.positions[0]).height,
    ).toBeCloseTo(
      source.cellHeight(CELL, 'post_mean')! * 2 + HIGHLIGHT_CLEARANCE_METRES,
      3,
    );
  });

  it('hides the outline for a cell outside the surface', () => {
    const { layer, lines, surface } = setup();
    layer.setSelection({
      artifactKey: surface.artifactKey,
      h3Index: '83754bfffffffff',
      kind: 'surface',
      row: 0,
    });
    expect(lines.get(1).show).toBe(false);
  });

  it('places an observation highlight on the render-tier surface height', () => {
    const { layer, points, source, surface } = setup();
    layer.setSelection({
      artifactKey: surface.artifactKey,
      kind: 'observation',
      sourceRecordId: 'map-surveys:1',
    });
    const point = points.get(1);
    expect(point.show).toBe(true);
    expect(
      Ellipsoid.WGS84.cartesianToCartographic(point.position).height,
    ).toBeCloseTo(
      source.cellHeight(CELL, 'post_mean')! * 2 + HIGHLIGHT_CLEARANCE_METRES,
      3,
    );
  });

  it('outlines a selected cell flat on the globe when elevation is off', () => {
    const { layer, lines, observations, source, surface } = setup();
    expect(source.cellHeight(CELL, 'post_mean')).toBeGreaterThan(0);
    layer.setArtifacts(source, observations, 'post_mean', false, 2);
    layer.setSelection({
      artifactKey: surface.artifactKey,
      h3Index: CELL,
      kind: 'surface',
      row: 0,
    });

    const selection = lines.get(1);
    expect(selection.show).toBe(true);
    expect(
      Ellipsoid.WGS84.cartesianToCartographic(selection.positions[0]).height,
    ).toBeCloseTo(HIGHLIGHT_CLEARANCE_METRES, 3);
  });

  it('hides both highlights when the surface is withdrawn', () => {
    const { layer, lines, observations, points, surface } = setup();
    layer.setHover(
      {
        artifactKey: surface.artifactKey,
        h3Index: CELL,
        kind: 'surface',
        row: 0,
      },
      true,
    );
    layer.setSelection({
      artifactKey: surface.artifactKey,
      kind: 'observation',
      sourceRecordId: 'map-surveys:1',
    });
    expect(lines.get(0).show).toBe(true);
    expect(points.get(1).show).toBe(true);

    layer.setArtifacts(null, observations, 'post_mean', false, 0);

    for (const index of [0, 1]) {
      expect(lines.get(index).show).toBe(false);
      expect(points.get(index).show).toBe(false);
    }
  });
});
