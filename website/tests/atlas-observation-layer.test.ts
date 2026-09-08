import { cellToLatLng, cellToVertexes, gridDisk, vertexToLatLng } from 'h3-js';
import { Cartesian3, Ellipsoid } from 'cesium';
import { describe, expect, it } from 'vitest';

import type { SurfaceArtifact, SurfaceCell } from '../src/atlas/contracts';
import {
  observationSurfaceAnchor,
  observationSurfacePlacement,
  STUD_ASPECT_RATIO,
  SYMBOL_CLEARANCE_METRES,
} from '../src/atlas/scene/observation-symbols';
import { SURFACE_CLEARANCE_METRES } from '../src/atlas/scene/surface-mesh';
import { heightForCell } from '../src/atlas/visual-encoding';

const baseCell: SurfaceCell = {
  dist_nearest_obs_km: 25,
  h3_index: '83754efffffffff',
  post_mean: 0.2,
  post_sd: 0.25,
  posterior_contraction: 0.8,
  q025: 0.1,
  q975: 0.3,
  support: 'observed',
};

function slopedSurface(baseValue = baseCell.post_mean): {
  point: { lat: number; lon: number };
  surface: SurfaceArtifact;
} {
  const neighborIndex = gridDisk(baseCell.h3_index, 1).find(
    (index) =>
      index !== baseCell.h3_index &&
      cellToVertexes(baseCell.h3_index).some((vertex) =>
        cellToVertexes(index).includes(vertex),
      ),
  );
  if (!neighborIndex) throw new Error('fixture needs an adjacent H3 cell');
  const selectedBase = { ...baseCell, post_mean: baseValue };
  const neighbor: SurfaceCell = {
    ...selectedBase,
    h3_index: neighborIndex,
    post_mean: 1,
    support: 'interpolated',
  };
  const sharedVertex = cellToVertexes(baseCell.h3_index).find((vertex) =>
    cellToVertexes(neighborIndex).includes(vertex),
  );
  if (!sharedVertex) throw new Error('fixture needs a shared H3 vertex');
  const [centerLat, centerLon] = cellToLatLng(baseCell.h3_index);
  const [vertexLat, vertexLon] = vertexToLatLng(sharedVertex);
  return {
    point: {
      lat: centerLat + (vertexLat - centerLat) * 0.88,
      lon: centerLon + (vertexLon - centerLon) * 0.88,
    },
    surface: {
      artifact: {
        metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
        resolution: 3,
      },
      cells: [selectedBase, neighbor],
    } as SurfaceArtifact,
  };
}

describe('observation surface anchors', () => {
  it('places a smooth-surface marker on the exact triangle beneath it', () => {
    const { point, surface } = slopedSurface();
    const anchor = observationSurfaceAnchor(
      point,
      surface,
      'post_mean',
      'triangles',
    );
    const placement = observationSurfacePlacement(anchor, point, 1);
    const cartographic = Ellipsoid.WGS84.cartesianToCartographic(
      placement.position,
    );

    expect(anchor.height).toBeGreaterThan(heightForCell(baseCell, [0, 1], 1));
    expect(cartographic.height).toBeCloseTo(
      anchor.height + SURFACE_CLEARANCE_METRES + SYMBOL_CLEARANCE_METRES,
      1,
    );
  });

  it('aligns a stud to the rendered triangle normal without disabling globe depth', () => {
    const { point, surface } = slopedSurface();
    const anchor = observationSurfaceAnchor(
      point,
      surface,
      'post_mean',
      'honmoon-fill',
    );
    const placement = observationSurfacePlacement(anchor, point, 1);
    const radial = Ellipsoid.WGS84.geodeticSurfaceNormal(
      placement.position,
      new Cartesian3(),
    );

    expect(Cartesian3.dot(placement.normal, radial)).toBeGreaterThan(0);
    expect(Cartesian3.equalsEpsilon(placement.normal, radial, 1e-5)).toBe(
      false,
    );
    expect(placement.eyeOffset.z).toBeLessThan(0);
  });

  it('samples a sloped mesh when the supported cell center is the domain minimum', () => {
    const { point, surface } = slopedSurface(0);
    const anchor = observationSurfaceAnchor(
      point,
      surface,
      'post_mean',
      'triangles',
    );

    expect(anchor.height).toBeGreaterThan(0);
    expect(anchor.triangle).not.toBeNull();
  });

  it('uses the flat cell top for non-smoothed surface geometry', () => {
    const { point, surface } = slopedSurface();
    const anchor = observationSurfaceAnchor(
      point,
      surface,
      'post_mean',
      'extruded',
    );
    const placement = observationSurfacePlacement(anchor, point, 1);
    const radial = Ellipsoid.WGS84.geodeticSurfaceNormal(
      placement.position,
      new Cartesian3(),
    );

    expect(anchor.height).toBe(heightForCell(baseCell, [0, 1], 1));
    expect(Cartesian3.equalsEpsilon(placement.normal, radial, 1e-12)).toBe(
      true,
    );
  });

  it('defines a low dome rather than a full circular sphere silhouette', () => {
    expect(STUD_ASPECT_RATIO).toBeGreaterThan(0.5);
    expect(STUD_ASPECT_RATIO).toBeLessThan(1);
  });
});
