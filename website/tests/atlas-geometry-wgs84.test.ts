import {
  BoundingSphere,
  Cartesian3,
  Ellipsoid,
  GeometryPipeline,
} from 'cesium';
import { describe, expect, it } from 'vitest';

import {
  boundingSphereOf,
  geodeticSurfaceNormal,
  geodeticToEcef,
  needsLongitudeSplit,
  normalizeInto,
  scaleToGeocentricSurface,
  surfacePointToDegrees,
} from '../src/atlas/geometry/wgs84';

const SAMPLES: readonly [number, number, number][] = [
  [0, 0, 0],
  [36.81, -1.29, 650],
  [-179.95, 71.4, 650],
  [179.95, -16.9, 1_050],
  [12.5, 89.999, 0],
  [-73.2, -55.9, 7_650],
];

describe('Cesium-free WGS84 arithmetic (fast-load §B.6.5)', () => {
  it.each(SAMPLES)(
    'matches Cartesian3.fromDegrees(%f, %f, %f) bit for bit',
    (lon, lat, height) => {
      const out = new Float64Array(3);
      geodeticToEcef(lon, lat, height, out);
      const expected = Cartesian3.fromDegrees(lon, lat, height);
      expect(Array.from(out)).toEqual([expected.x, expected.y, expected.z]);
    },
  );

  it('normalises like Cartesian3.normalize', () => {
    const position = Cartesian3.fromDegrees(36.81, -1.29, 650);
    const out = new Float64Array(3);
    normalizeInto([position.x, position.y, position.z], 0, out);
    const expected = Cartesian3.normalize(position, new Cartesian3());
    expect(Array.from(out)).toEqual([expected.x, expected.y, expected.z]);
  });

  it('matches the ellipsoid normal and geocentric scaling', () => {
    const position = Cartesian3.fromDegrees(-73.2, -55.9, 400_000);
    const normal = Ellipsoid.WGS84.geodeticSurfaceNormal(
      position,
      new Cartesian3(),
    );
    expect(geodeticSurfaceNormal([position.x, position.y, position.z])).toEqual(
      [normal.x, normal.y, normal.z],
    );
    const scaled = Ellipsoid.WGS84.scaleToGeocentricSurface(
      position,
      new Cartesian3(),
    );
    expect(
      scaleToGeocentricSurface([position.x, position.y, position.z]),
    ).toEqual([scaled.x, scaled.y, scaled.z]);
  });

  it('recovers geodetic degrees of a surface point', () => {
    const surface = Cartesian3.fromDegrees(141.3, 43.06, 0);
    const { lat, lon } = surfacePointToDegrees([
      surface.x,
      surface.y,
      surface.z,
    ]);
    expect(lat).toBeCloseTo(43.06, 10);
    expect(lon).toBeCloseTo(141.3, 10);
  });

  it('builds the same sphere as BoundingSphere.fromVertices over every set', () => {
    const first = new Float64Array(SAMPLES.length * 3);
    SAMPLES.forEach(([lon, lat, height], index) =>
      geodeticToEcef(lon, lat, height, first, index * 3),
    );
    const second = first.map((value) => value * 1.1);
    const expected = BoundingSphere.fromVertices([...first, ...second]);
    const sphere = boundingSphereOf([first, second]);
    expect(sphere.radius).toBe(expected.radius);
    expect(sphere.center).toEqual([
      expected.center.x,
      expected.center.y,
      expected.center.z,
    ]);
    expect(boundingSphereOf([])).toEqual({ center: [0, 0, 0], radius: 0 });
  });

  it('predicts exactly when splitLongitude leaves its early exit', () => {
    const spheres = [
      { center: [6_000_000, 0, 0], radius: 1_000_000 },
      { center: [-6_000_000, 10, 0], radius: 1_000_000 },
      { center: [-6_000_000, 2_000_000, 0], radius: 1_000_000 },
      { center: [-6_000_000, -1_000_000, 0], radius: 1_000_000 },
    ] as const;
    const splitLongitude = (
      GeometryPipeline as unknown as { splitLongitude(value: unknown): unknown }
    ).splitLongitude;
    for (const sphere of spheres) {
      let walked = false;
      const geometry = {
        boundingSphere: new BoundingSphere(
          Cartesian3.fromArray([...sphere.center]),
          sphere.radius,
        ),
        get geometryType(): never {
          walked = true;
          throw new Error('past the early exit');
        },
      };
      try {
        splitLongitude({ geometry });
      } catch {
        // The sentinel getter throws once the early exit has been skipped.
      }
      expect(
        needsLongitudeSplit({
          center: [...sphere.center],
          radius: sphere.radius,
        }),
        JSON.stringify(sphere),
      ).toBe(walked);
    }
  });
});
