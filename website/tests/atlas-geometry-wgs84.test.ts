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
  magnitude,
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

/** Ground and raised rings of a hexagon `spanDegrees` around a centre, as the
 * two position sets a surface chunk passes to `boundingSphereOf`. */
function hexagonSets(
  lon: number,
  lat: number,
  spanDegrees: number,
): [Float64Array, Float64Array] {
  const ground = new Float64Array(18);
  const raised = new Float64Array(18);
  for (let corner = 0; corner < 6; corner += 1) {
    const angle = (corner * Math.PI) / 3;
    const cornerLon = lon + spanDegrees * Math.cos(angle);
    const cornerLat = lat + spanDegrees * Math.sin(angle);
    geodeticToEcef(cornerLon, cornerLat, 0, ground, corner * 3);
    geodeticToEcef(cornerLon, cornerLat, 650, raised, corner * 3);
  }
  return [ground, raised];
}

/** Centre of the axis-aligned box over every triple: `fromVertices`' naive centre. */
function boxMidpoint(sets: readonly ArrayLike<number>[]): number[] {
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  for (const positions of sets)
    for (let i = 0; i < positions.length; i += 3)
      for (let axis = 0; axis < 3; axis += 1) {
        low[axis] = Math.min(low[axis], positions[i + axis]);
        high[axis] = Math.max(high[axis], positions[i + axis]);
      }
  return low.map((value, axis) => (value + high[axis]) * 0.5);
}

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

  it('normalises the triple at sourceOffset into out at offset', () => {
    const source = new Float64Array(9);
    geodeticToEcef(0, 0, 0, source, 0);
    geodeticToEcef(36.81, -1.29, 650, source, 3);
    geodeticToEcef(-73.2, -55.9, 7_650, source, 6);
    const out = new Float64Array(9).fill(-1);
    normalizeInto(source, 3, out, 6);
    const expected = Cartesian3.normalize(
      Cartesian3.fromDegrees(36.81, -1.29, 650),
      new Cartesian3(),
    );
    expect(Array.from(out)).toEqual([
      -1,
      -1,
      -1,
      -1,
      -1,
      -1,
      expected.x,
      expected.y,
      expected.z,
    ]);
  });

  it('measures length like Cartesian3.magnitude', () => {
    for (const [lon, lat, height] of SAMPLES) {
      const position = Cartesian3.fromDegrees(lon, lat, height);
      expect(magnitude([position.x, position.y, position.z])).toBe(
        Cartesian3.magnitude(position),
      );
    }
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

  it.each([
    { winner: 'Ritter', lon: 36.81, lat: -1.29 },
    { winner: 'naive', lon: 141.3, lat: 43.06 },
  ])(
    'keeps the smaller sphere like BoundingSphere.fromVertices ($winner wins)',
    ({ winner, lon, lat }) => {
      const sets = hexagonSets(lon, lat, 2);
      const expected = BoundingSphere.fromVertices([...sets[0], ...sets[1]]);
      const sphere = boundingSphereOf(sets);
      expect(sphere.radius).toBe(expected.radius);
      expect(sphere.center).toEqual([
        expected.center.x,
        expected.center.y,
        expected.center.z,
      ]);
      // The naive sphere is centred on the box midpoint; Ritter's is not.
      const midpoint = boxMidpoint(sets);
      expect(sphere.center.every((v, axis) => v === midpoint[axis])).toBe(
        winner === 'naive',
      );
    },
  );

  it('skips empty sets and refuses a set with a partial xyz triple', () => {
    const [ground, raised] = hexagonSets(36.81, -1.29, 2);
    expect(boundingSphereOf([[], ground, new Float64Array(0), raised])).toEqual(
      boundingSphereOf([ground, raised]),
    );
    expect(() => boundingSphereOf([ground, raised.subarray(0, 17)])).toThrow(
      'boundingSphereOf: set 1 holds 17 values, not a whole number of xyz triples',
    );
    expect(() => boundingSphereOf([[1, 2]])).toThrow(
      'boundingSphereOf: set 0 holds 2 values, not a whole number of xyz triples',
    );
  });

  it('predicts exactly when splitLongitude leaves its early exit', () => {
    // `splits`: whether Cesium walks past the early exit for this sphere.
    const spheres = [
      // minX > 0: early exit.
      { center: [6_000_000, 0, 0], radius: 1_000_000, splits: false },
      // minX === 0 is not > 0, and the sphere straddles the ZX plane.
      { center: [1_000_000, 0, 0], radius: 1_000_000, splits: true },
      { center: [-6_000_000, 10, 0], radius: 1_000_000, splits: true },
      // Wholly on the +y side (INSIDE): early exit.
      { center: [-6_000_000, 2_000_000, 0], radius: 1_000_000, splits: false },
      // y === +radius is INSIDE, not INTERSECTING: early exit.
      { center: [-6_000_000, 1_000_000, 0], radius: 1_000_000, splits: false },
      // y === -radius is INTERSECTING.
      { center: [-6_000_000, -1_000_000, 0], radius: 1_000_000, splits: true },
      // Wholly on the -y side (OUTSIDE): early exit.
      { center: [-6_000_000, -2_000_000, 0], radius: 1_000_000, splits: false },
    ] as const;
    const splitLongitude = (
      GeometryPipeline as unknown as { splitLongitude(value: unknown): unknown }
    ).splitLongitude;
    const pastEarlyExit = new Error('past the early exit');
    for (const sphere of spheres) {
      const label = JSON.stringify(sphere);
      let walked = false;
      const instance = {
        geometry: {
          boundingSphere: new BoundingSphere(
            Cartesian3.fromArray([...sphere.center]),
            sphere.radius,
          ),
          get geometryType(): never {
            walked = true;
            throw pastEarlyExit;
          },
        },
      };
      let returned: unknown = pastEarlyExit;
      try {
        returned = splitLongitude(instance);
      } catch (error) {
        // Only the sentinel getter's throw means "past the early exit".
        if (error !== pastEarlyExit) throw error;
      }
      expect(walked, label).toBe(sphere.splits);
      // The early exit hands back the instance it was given, untouched.
      expect(returned, label).toBe(walked ? pastEarlyExit : instance);
      expect(
        needsLongitudeSplit({
          center: [...sphere.center],
          radius: sphere.radius,
        }),
        label,
      ).toBe(walked);
    }
  });
});
