/** Cesium-free WGS84 arithmetic for the Atlas data worker (fast-load spec
 * 2026-10-07 §B.6.5–§B.6.6).
 *
 * Each function repeats the Cesium 1.145 operation named in its comment term
 * for term (same operands, same order), so worker buffers equal the legacy
 * main-thread `Cartesian3` results bit for bit. Distances are metres.
 */

const RADIUS_X = 6378137.0;
const RADIUS_Y = 6378137.0;
const RADIUS_Z = 6356752.3142451793;
const RADII_SQUARED_X = RADIUS_X * RADIUS_X;
const RADII_SQUARED_Y = RADIUS_Y * RADIUS_Y;
const RADII_SQUARED_Z = RADIUS_Z * RADIUS_Z;
const ONE_OVER_RADII_SQUARED_X = 1.0 / (RADIUS_X * RADIUS_X);
const ONE_OVER_RADII_SQUARED_Y = 1.0 / (RADIUS_Y * RADIUS_Y);
const ONE_OVER_RADII_SQUARED_Z = 1.0 / (RADIUS_Z * RADIUS_Z);
const RADIANS_PER_DEGREE = Math.PI / 180.0;
const DEGREES_PER_RADIAN = 180.0 / Math.PI;

export type Vec3 = [number, number, number];

/** `Cartesian3.fromDegrees(lon, lat, height)` on WGS84, written into `out`. */
export function geodeticToEcef(
  lonDegrees: number,
  latDegrees: number,
  height: number,
  out: Float64Array | number[],
  offset = 0,
): void {
  const longitude = lonDegrees * RADIANS_PER_DEGREE;
  const latitude = latDegrees * RADIANS_PER_DEGREE;
  const cosLatitude = Math.cos(latitude);
  let nx = cosLatitude * Math.cos(longitude);
  let ny = cosLatitude * Math.sin(longitude);
  let nz = Math.sin(latitude);
  const magnitude = Math.sqrt(nx * nx + ny * ny + nz * nz);
  nx = nx / magnitude;
  ny = ny / magnitude;
  nz = nz / magnitude;
  let kx = RADII_SQUARED_X * nx;
  let ky = RADII_SQUARED_Y * ny;
  let kz = RADII_SQUARED_Z * nz;
  const gamma = Math.sqrt(nx * kx + ny * ky + nz * kz);
  kx = kx / gamma;
  ky = ky / gamma;
  kz = kz / gamma;
  out[offset] = kx + nx * height;
  out[offset + 1] = ky + ny * height;
  out[offset + 2] = kz + nz * height;
}

/** `Cartesian3.normalize`: divides each component by the magnitude. */
export function normalizeInto(
  source: ArrayLike<number>,
  sourceOffset: number,
  out: Float64Array | Float32Array | number[],
  offset = 0,
): void {
  const x = source[sourceOffset];
  const y = source[sourceOffset + 1];
  const z = source[sourceOffset + 2];
  const magnitude = Math.sqrt(x * x + y * y + z * z);
  out[offset] = x / magnitude;
  out[offset + 1] = y / magnitude;
  out[offset + 2] = z / magnitude;
}

/** `Ellipsoid.WGS84.geodeticSurfaceNormal(position)`. */
export function geodeticSurfaceNormal(position: ArrayLike<number>): Vec3 {
  const x = position[0] * ONE_OVER_RADII_SQUARED_X;
  const y = position[1] * ONE_OVER_RADII_SQUARED_Y;
  const z = position[2] * ONE_OVER_RADII_SQUARED_Z;
  const magnitude = Math.sqrt(x * x + y * y + z * z);
  return [x / magnitude, y / magnitude, z / magnitude];
}

/** `Ellipsoid.WGS84.scaleToGeocentricSurface(position)`. */
export function scaleToGeocentricSurface(position: ArrayLike<number>): Vec3 {
  const x = position[0];
  const y = position[1];
  const z = position[2];
  const beta =
    1.0 /
    Math.sqrt(
      x * x * ONE_OVER_RADII_SQUARED_X +
        y * y * ONE_OVER_RADII_SQUARED_Y +
        z * z * ONE_OVER_RADII_SQUARED_Z,
    );
  return [x * beta, y * beta, z * beta];
}

/** Geodetic degrees of a point lying on the ellipsoid surface. */
export function surfacePointToDegrees(point: ArrayLike<number>): {
  lat: number;
  lon: number;
} {
  const [nx, ny, nz] = geodeticSurfaceNormal(point);
  return {
    lat: Math.asin(nz) * DEGREES_PER_RADIAN,
    lon: Math.atan2(ny, nx) * DEGREES_PER_RADIAN,
  };
}

export function magnitude(vector: ArrayLike<number>): number {
  return Math.sqrt(
    vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2],
  );
}

export interface BoundingSphere {
  center: [number, number, number];
  radius: number;
}

/** Overwrites `target` in place, so a new extremum allocates nothing. */
function assignVec3(target: Vec3, x: number, y: number, z: number): void {
  target[0] = x;
  target[1] = y;
  target[2] = z;
}

/** `BoundingSphere.fromVertices` (Ritter plus naive box; the smaller wins),
 * taken over every xyz triple of every array in `sets`, in order.
 *
 * Throws when a set's length is not a multiple of 3: a partial triple is a
 * malformed buffer, and dropping it would bound fewer vertices than the chunk
 * draws. Empty sets are skipped; no vertices at all gives a zero sphere at the
 * origin, as Cesium does for an empty array. */
export function boundingSphereOf(
  sets: readonly ArrayLike<number>[],
): BoundingSphere {
  let first = -1;
  for (let index = 0; index < sets.length; index += 1) {
    const { length } = sets[index];
    if (length % 3 !== 0)
      throw new Error(
        `boundingSphereOf: set ${index} holds ${length} values, not a whole number of xyz triples`,
      );
    if (first < 0 && length > 0) first = index;
  }
  if (first < 0) return { center: [0, 0, 0], radius: 0 };
  const start = sets[first];
  const xMin: Vec3 = [start[0], start[1], start[2]];
  const yMin: Vec3 = [start[0], start[1], start[2]];
  const zMin: Vec3 = [start[0], start[1], start[2]];
  const xMax: Vec3 = [start[0], start[1], start[2]];
  const yMax: Vec3 = [start[0], start[1], start[2]];
  const zMax: Vec3 = [start[0], start[1], start[2]];
  for (const positions of sets)
    for (let i = 0; i < positions.length; i += 3) {
      const x = positions[i];
      const y = positions[i + 1];
      const z = positions[i + 2];
      if (x < xMin[0]) assignVec3(xMin, x, y, z);
      if (x > xMax[0]) assignVec3(xMax, x, y, z);
      if (y < yMin[1]) assignVec3(yMin, x, y, z);
      if (y > yMax[1]) assignVec3(yMax, x, y, z);
      if (z < zMin[2]) assignVec3(zMin, x, y, z);
      if (z > zMax[2]) assignVec3(zMax, x, y, z);
    }
  const span = (a: Vec3, b: Vec3): number =>
    (b[0] - a[0]) * (b[0] - a[0]) +
    (b[1] - a[1]) * (b[1] - a[1]) +
    (b[2] - a[2]) * (b[2] - a[2]);
  const xSpan = span(xMin, xMax);
  const ySpan = span(yMin, yMax);
  const zSpan = span(zMin, zMax);
  let diameter1 = xMin;
  let diameter2 = xMax;
  let maxSpan = xSpan;
  if (ySpan > maxSpan) {
    maxSpan = ySpan;
    diameter1 = yMin;
    diameter2 = yMax;
  }
  if (zSpan > maxSpan) {
    diameter1 = zMin;
    diameter2 = zMax;
  }
  const ritter: Vec3 = [
    (diameter1[0] + diameter2[0]) * 0.5,
    (diameter1[1] + diameter2[1]) * 0.5,
    (diameter1[2] + diameter2[2]) * 0.5,
  ];
  let radiusSquared = span(ritter, diameter2);
  let ritterRadius = Math.sqrt(radiusSquared);
  const naive: Vec3 = [
    (xMin[0] + xMax[0]) * 0.5,
    (yMin[1] + yMax[1]) * 0.5,
    (zMin[2] + zMax[2]) * 0.5,
  ];
  let naiveRadius = 0;
  for (const positions of sets)
    for (let i = 0; i < positions.length; i += 3) {
      const x = positions[i];
      const y = positions[i + 1];
      const z = positions[i + 2];
      const r = Math.sqrt(
        (x - naive[0]) * (x - naive[0]) +
          (y - naive[1]) * (y - naive[1]) +
          (z - naive[2]) * (z - naive[2]),
      );
      if (r > naiveRadius) naiveRadius = r;
      const oldCenterToPointSquared =
        (x - ritter[0]) * (x - ritter[0]) +
        (y - ritter[1]) * (y - ritter[1]) +
        (z - ritter[2]) * (z - ritter[2]);
      if (oldCenterToPointSquared > radiusSquared) {
        const oldCenterToPoint = Math.sqrt(oldCenterToPointSquared);
        ritterRadius = (ritterRadius + oldCenterToPoint) * 0.5;
        radiusSquared = ritterRadius * ritterRadius;
        const oldToNew = oldCenterToPoint - ritterRadius;
        ritter[0] =
          (ritterRadius * ritter[0] + oldToNew * x) / oldCenterToPoint;
        ritter[1] =
          (ritterRadius * ritter[1] + oldToNew * y) / oldCenterToPoint;
        ritter[2] =
          (ritterRadius * ritter[2] + oldToNew * z) / oldCenterToPoint;
      }
    }
  return ritterRadius < naiveRadius
    ? { center: ritter, radius: ritterRadius }
    : { center: naive, radius: naiveRadius };
}

/** True when Cesium's `GeometryPipeline.splitLongitude` cannot take its early
 * exit for this sphere (`minX > 0` or no ZX-plane crossing), i.e. the chunk
 * pays the per-triangle antimeridian pass on first render. */
export function needsLongitudeSplit(sphere: BoundingSphere): boolean {
  const minX = sphere.center[0] - sphere.radius;
  const distanceToPlane = sphere.center[1];
  const crossesZxPlane =
    !(distanceToPlane < -sphere.radius) && distanceToPlane < sphere.radius;
  return !(minX > 0 || !crossesZxPlane);
}
