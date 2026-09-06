import { cellToBoundary } from 'h3-js';
import {
  Cartesian3,
  MaterialAppearance,
  PolygonGeometry,
  PolygonHierarchy,
} from 'cesium';
import { describe, expect, it } from 'vitest';

import type { SurfaceArtifact, SurfaceCell } from '../src/atlas/contracts';
import { cameraState, keyboardCommandFor } from '../src/atlas/scene/camera';
import { LayerCache } from '../src/atlas/scene/layer-cache';
import { observationPickId } from '../src/atlas/scene/observation-layer';
import {
  h3BoundaryDegrees,
  h3PolygonParts,
  surfacePickId,
} from '../src/atlas/scene/surface-layer';
import {
  partitionSurfaceCells,
  quantizeMetric,
} from '../src/atlas/scene/support-material';
import {
  preferredAtlasPick,
  resolveElevationView,
  transitionProgress,
} from '../src/atlas/scene/atlas-scene';

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

describe('Cesium scene policy', () => {
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

  it('prefers a measured point when it overlaps a modeled cell', () => {
    const surface = { id: surfacePickId(baseCell) };
    const observation = { id: observationPickId('map-surveys:1') };
    expect(preferredAtlasPick([surface, observation])).toEqual(observation.id);
    expect(preferredAtlasPick([surface])).toEqual(surface.id);
    expect(preferredAtlasPick([{ id: 'context' }])).toBeNull();
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
});
