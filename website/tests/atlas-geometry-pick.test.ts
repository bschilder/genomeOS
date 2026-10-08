import {
  cellToBoundary,
  cellToLatLng,
  cellToVertexes,
  cellsToDirectedEdge,
  directedEdgeToBoundary,
  gridDisk,
  latLngToCell,
  vertexToLatLng,
} from 'h3-js';
import { describe, expect, it, vi } from 'vitest';

import { resolveSurfaceRow } from '../src/atlas/geometry/pick-resolver';
import {
  buildSurfaceChunk,
  SURFACE_CLEARANCE_METRES,
  type MeshInput,
  type SurfaceChunkBuffers,
} from '../src/atlas/geometry/surface-buffers';
import { geodeticToEcef, magnitude } from '../src/atlas/geometry/wgs84';
import { renderAt, type SurfaceArtifact } from '../src/atlas/surface-columns';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import { heightFor } from '../src/atlas/visual-encoding';
import {
  meshInputFor,
  sortedU64,
  wholeGridChunk,
  type TestCell,
} from './helpers/mesh-input';

// h3-js stays real everywhere. The spy only lets the tie-break test give
// several neighbours one centre: no real grid has an exact distance tie.
vi.mock('h3-js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('h3-js')>();
  return { ...actual, cellToLatLng: vi.fn(actual.cellToLatLng) };
});

const RESOLUTION = 3;
const CENTRE = '83754efffffffff';
/** `latLngToCell(45, 10, 3)`. At 45°N the geocentric radial and the geodetic
 * normal differ by about 0.19°, so a geodetic projection of a lifted point can
 * land in the next cell; at CENTRE (0.4°N) it never does. */
const MID_LATITUDE = '831ea6fffffffff';
const DISK = sortedU64(gridDisk(CENTRE, 1));
const TALL = 0.9;
const SHORT = 0.2;
const GEOMETRIES = ['triangles', 'honmoon', 'hexagons'] as const;

/** `[lat, lon]` in degrees, the order h3-js uses. */
type Degrees = [number, number];
type Cartesian = [number, number, number];

function setup(
  geometry: SurfaceGeometry,
  centre = CENTRE,
  cellOf: (h3: string) => Omit<TestCell, 'h3'> = (h3) => ({
    support: 'interpolated',
    value: h3 === centre ? TALL : SHORT,
  }),
): {
  disk: string[];
  input: MeshInput;
  surface: SurfaceArtifact;
  buffers: SurfaceChunkBuffers;
  heights: (row: number) => number;
} {
  const disk = sortedU64(gridDisk(centre, 1));
  const input = meshInputFor(
    disk.map((h3) => ({ h3, ...cellOf(h3) })),
    { geometry },
  );
  const surface = {
    artifact: {
      metric_domains: { post_mean: [0, 1], post_sd: [0, 1] },
      resolution: RESOLUTION,
    },
    artifactKey: 'fixture:v1:d1',
    detail: null,
    grid: input.grid,
    support: input.support,
    values: { post_mean: input.values, post_sd: input.values },
  } as unknown as SurfaceArtifact;
  return {
    buffers: buildSurfaceChunk(input, wholeGridChunk(input)),
    disk,
    // The scene's callback (contract): render tier, exaggeration 1, 0 masked.
    heights: (row) => {
      const cell = renderAt(surface, row);
      return heightFor(cell.support, cell.post_mean, [0, 1], 1);
    },
    input,
    surface,
  };
}

function displaced(
  buffers: SurfaceChunkBuffers,
  vertex: number,
  factor: number,
): number[] {
  return [0, 1, 2].map(
    (axis) =>
      buffers.positions[vertex * 3 + axis] +
      buffers.elevationNormals[vertex * 3 + axis] *
        buffers.heights[vertex] *
        factor,
  );
}

function blend(
  points: readonly number[][],
  weights: readonly number[],
): Cartesian {
  return [0, 1, 2].map((axis) =>
    points.reduce(
      (total, point, index) => total + point[axis] * weights[index],
      0,
    ),
  ) as Cartesian;
}

/** The point `altitude` metres above the surface clearance over `ground`,
 * along the geocentric radial: the resolver's hit altitude is `altitude`. */
function lifted([lat, lon]: Degrees, altitude: number): Cartesian {
  const ground = [0, 0, 0];
  geodeticToEcef(lon, lat, 0, ground);
  const scale = 1 + (SURFACE_CLEARANCE_METRES + altitude) / magnitude(ground);
  return ground.map((axis) => axis * scale) as Cartesian;
}

function chord(from: Degrees, to: Degrees): number {
  const [a, b] = [from, to].map(([lat, lon]) => {
    const point = [0, 0, 0];
    geodeticToEcef(lon, lat, 0, point);
    return point;
  });
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** A ground point inside `cell`, 3% of the way short of its edge with
 * `other` (asserted inside `cell`, so each case exercises the branch named). */
function besideEdge(cell: string, other: string): Degrees {
  const [[firstLat, firstLon], [secondLat, secondLon]] = directedEdgeToBoundary(
    cellsToDirectedEdge(cell, other),
  );
  const [lat, lon] = cellToLatLng(cell);
  const point: Degrees = [
    lat + ((firstLat + secondLat) / 2 - lat) * 0.97,
    lon + ((firstLon + secondLon) / 2 - lon) * 0.97,
  ];
  expect(latLngToCell(point[0], point[1], RESOLUTION), 'precondition').toBe(
    cell,
  );
  return point;
}

/** Geodetic `[lat, lon]` of any ECEF point (Bowring iteration): the projection
 * Cesium's `cartesianToCartographic` makes. A test oracle only, showing that
 * the 45°N fixture separates the geodetic and the geocentric projection. */
function geodeticDegrees([x, y, z]: readonly number[]): Degrees {
  const a = 6378137;
  const b = 6356752.3142451793;
  const e2 = 1 - (b * b) / (a * a);
  const radius = Math.hypot(x, y);
  let lat = Math.atan2(z, radius * (1 - e2));
  for (let step = 0; step < 10; step += 1) {
    const n = a / Math.sqrt(1 - e2 * Math.sin(lat) ** 2);
    const height = radius / Math.cos(lat) - n;
    lat = Math.atan2(z, radius * (1 - (e2 * n) / (n + height)));
  }
  return [(lat * 180) / Math.PI, (Math.atan2(y, x) * 180) / Math.PI];
}

function extrudedPick(
  surface: SurfaceArtifact,
  heights: (row: number) => number,
  factor: number,
): (cartesian: Cartesian) => number | null {
  return (cartesian) =>
    resolveSurfaceRow(
      {
        cartesian,
        clearance: SURFACE_CLEARANCE_METRES,
        ellipsoidHit: null,
        factor,
        geometry: 'extruded',
      },
      surface,
      heights,
    );
}

/** Points blended from every exaggeration-5 fan triangle of the disk around
 * `centre` resolve to their own row. Returns how many of them a geodetic
 * projection would have put in another cell. */
function expectNearEdgePicks(
  geometry: (typeof GEOMETRIES)[number],
  centre: string,
): number {
  const { disk, surface, buffers, heights, input } = setup(geometry, centre);
  let triangle = 0;
  let geodeticMisses = 0;
  disk.forEach((h3, row) => {
    const corners =
      input.topology.cornerOffsets[row + 1] - input.topology.cornerOffsets[row];
    for (let corner = 0; corner < corners; corner += 1, triangle += 1) {
      const vertices = [0, 1, 2].map((offset) =>
        displaced(buffers, buffers.indices[triangle * 3 + offset], 5),
      );
      for (const weights of [
        [0.02, 0.49, 0.49],
        [0.005, 0.4975, 0.4975],
        [0.02, 0.9, 0.08],
        [0.34, 0.33, 0.33],
      ]) {
        const cartesian = blend(vertices, weights);
        expect(
          resolveSurfaceRow(
            {
              cartesian,
              clearance: SURFACE_CLEARANCE_METRES,
              ellipsoidHit: null,
              factor: 5,
              geometry,
            },
            surface,
            heights,
          ),
          `${h3} triangle ${corner} ${weights}`,
        ).toBe(row);
        const [lat, lon] = geodeticDegrees(cartesian);
        if (latLngToCell(lat, lon, RESOLUTION) !== h3) geodeticMisses += 1;
      }
    }
  });
  return geodeticMisses;
}

describe('surface pick resolution (fast-load §B.6.6)', () => {
  it('reads the ellipsoid hit at elevation factor 0', () => {
    const { surface, heights } = setup('triangles');
    DISK.forEach((h3, row) => {
      const [lat, lon] = cellToLatLng(h3);
      const pick = (hit: { lat: number; lon: number } | null) =>
        resolveSurfaceRow(
          {
            cartesian: null,
            clearance: SURFACE_CLEARANCE_METRES,
            ellipsoidHit: hit,
            factor: 0,
            geometry: 'triangles',
          },
          surface,
          heights,
        );
      expect(pick({ lat, lon })).toBe(row);
      for (const [vertexLat, vertexLon] of cellToBoundary(h3))
        expect(
          pick({
            lat: lat + (vertexLat - lat) * 0.99,
            lon: lon + (vertexLon - lon) * 0.99,
          }),
        ).toBe(row);
      expect(pick(null)).toBeNull();
    });
    expect(
      resolveSurfaceRow(
        {
          cartesian: null,
          clearance: SURFACE_CLEARANCE_METRES,
          ellipsoidHit: { lat: -60, lon: -30 },
          factor: 0,
          geometry: 'triangles',
        },
        surface,
        heights,
      ),
    ).toBeNull();
  });

  it.each(['triangles', 'hexagons', 'extruded'] as const)(
    'returns null without a picked position or off the grid at exaggeration 5 (%s)',
    (geometry) => {
      const { surface } = setup(geometry);
      const [lat, lon] = cellToLatLng(CENTRE);
      // Neither case reaches the heights; only `extruded` ever reads them.
      const unread = (): number => {
        throw new Error('heights read');
      };
      const pick = (
        cartesian: Cartesian | null,
        heights: (row: number) => number = unread,
      ) =>
        resolveSurfaceRow(
          {
            cartesian,
            clearance: SURFACE_CLEARANCE_METRES,
            // Ignored above factor 0, even when it lies on the grid.
            ellipsoidHit: { lat, lon },
            factor: 5,
            geometry,
          },
          surface,
          heights,
        );
      expect(pick(null)).toBeNull();
      expect(pick(lifted([-60, -30], 1_000))).toBeNull();
      if (geometry !== 'extruded')
        expect(pick(lifted([lat, lon], 500_000))).toBe(DISK.indexOf(CENTRE));
    },
  );

  it.each(GEOMETRIES)(
    'undoes the radial lift near cell edges at exaggeration 5 (%s)',
    (geometry) => {
      expectNearEdgePicks(geometry, CENTRE);
    },
  );

  it.each(GEOMETRIES)(
    'projects along the geocentric radial, not the geodetic normal, at 45°N (%s)',
    (geometry) => {
      expect(
        expectNearEdgePicks(geometry, MID_LATITUDE),
        'picks that a geodetic projection puts in another cell',
      ).toBeGreaterThan(0);
    },
  );

  it.each([1, 5])(
    'gives extruded wall hits to the taller cell at exaggeration %d',
    (factor) => {
      const { surface, buffers, heights, input } = setup('extruded');
      const centreRow = DISK.indexOf(CENTRE);
      const { cornerOffsets } = input.topology;
      let base = 0;
      for (let row = 0; row < centreRow; row += 1) {
        const count = cornerOffsets[row + 1] - cornerOffsets[row];
        base += 1 + count * 5;
      }
      const corners = cellToVertexes(CENTRE);
      const resolve = extrudedPick(surface, heights, factor);
      const tallHeight = Math.fround(heights(centreRow));
      // Precondition on Task 44's extruded layout: the centre cell's top
      // centre vertex sits at `base`.
      expect(buffers.heights[base], 'top centre vertex').toBe(tallHeight);
      let walls = 0;
      for (const neighbour of DISK.filter((cell) => cell !== CENTRE)) {
        const neighbourRow = DISK.indexOf(neighbour);
        const shared = cellToVertexes(neighbour);
        const corner = corners.findIndex(
          (vertex, index) =>
            shared.includes(vertex) &&
            shared.includes(corners[(index + 1) % corners.length]),
        );
        expect(corner, neighbour).toBeGreaterThanOrEqual(0);
        const wall = base + 1 + corners.length + corner * 4;
        // Preconditions: the four vertices at `wall` are this shared edge's
        // quad (bottom, bottom, top, top), with the bottoms at its two corners.
        expect(
          [0, 1, 2, 3].map((offset) => buffers.heights[wall + offset]),
          `${neighbour} wall heights`,
        ).toEqual([0, 0, tallHeight, tallHeight]);
        [corners[corner], corners[(corner + 1) % corners.length]].forEach(
          (vertex, offset) => {
            const [vertexLat, vertexLon] = vertexToLatLng(vertex);
            const foot = [0, 0, 0];
            geodeticToEcef(
              vertexLon,
              vertexLat,
              SURFACE_CLEARANCE_METRES,
              foot,
            );
            const gap = Math.hypot(
              ...[0, 1, 2].map(
                (axis) =>
                  buffers.positions[(wall + offset) * 3 + axis] - foot[axis],
              ),
            );
            expect(gap, `${neighbour} wall foot ${offset}`).toBeLessThan(1e-3);
          },
        );
        const [bottomFirst, bottomSecond, topFirst, topSecond] = [
          0, 1, 2, 3,
        ].map((offset) => displaced(buffers, wall + offset, factor));
        const shortTop = heights(neighbourRow) * factor;
        const tallTop = heights(centreRow) * factor;
        for (const along of [0.3, 0.5, 0.7])
          for (const up of [0.25, 0.5, 0.9]) {
            const altitude = shortTop + 10 + (tallTop - shortTop - 20) * up;
            const fraction = altitude / (tallTop + 1);
            const point = blend(
              [bottomFirst, bottomSecond, topFirst, topSecond],
              [
                (1 - along) * (1 - fraction),
                along * (1 - fraction),
                (1 - along) * fraction,
                along * fraction,
              ],
            );
            expect(resolve(point), `${neighbour} wall ${along} ${up}`).toBe(
              centreRow,
            );
          }
        const [lat, lon] = cellToLatLng(neighbour);
        const [vertexLat, vertexLon] = vertexToLatLng(corners[corner]);
        const nearEdge = [0, 0, 0];
        geodeticToEcef(
          lon + (vertexLon - lon) * 0.97,
          lat + (vertexLat - lat) * 0.97,
          SURFACE_CLEARANCE_METRES + 1 + shortTop,
          nearEdge,
        );
        expect(resolve(nearEdge as Cartesian), `${neighbour} top`).toBe(
          neighbourRow,
        );
        walls += 1;
      }
      expect(walls).toBe(6);
    },
  );

  it.each([1, 5])(
    'gives a wall hit to the nearest neighbour tall enough, not the tallest or the first, at exaggeration %d',
    (factor) => {
      // The centre is the shortest cell and the ring rises with its row, so
      // for five of the six walls the tallest neighbour, and the first that
      // gridDisk visits, are not the nearest one.
      const ring = DISK.filter((cell) => cell !== CENTRE);
      const { surface, heights } = setup('extruded', CENTRE, (h3) => ({
        support: 'interpolated',
        value: h3 === CENTRE ? 0.1 : 0.4 + 0.1 * ring.indexOf(h3),
      }));
      const resolve = extrudedPick(surface, heights, factor);
      const lowestRingTop = Math.min(
        ...ring.map((cell) => heights(DISK.indexOf(cell))),
      );
      // Above the centre's top, below every ring top: every neighbour qualifies.
      const altitude =
        ((heights(DISK.indexOf(CENTRE)) + lowestRingTop) / 2) * factor;
      expect(
        ring.map((neighbour) =>
          resolve(lifted(besideEdge(CENTRE, neighbour), altitude)),
        ),
      ).toEqual(ring.map((neighbour) => DISK.indexOf(neighbour)));
    },
  );

  it.each([1, 5])(
    'skips masked and short neighbours and falls back to the projected row at exaggeration %d',
    (factor) => {
      const ring = DISK.filter((cell) => cell !== CENTRE);
      const masked = ring[0];
      const short = ring.find(
        (cell) => cell !== masked && gridDisk(masked, 1).includes(cell),
      );
      if (short === undefined)
        throw new Error('precondition: a ring cell borders the masked one');
      const { surface, heights } = setup('extruded', CENTRE, (h3) => ({
        support: h3 === masked ? 'unknown' : 'interpolated',
        value: h3 === CENTRE ? TALL : SHORT,
      }));
      const resolve = extrudedPick(surface, heights, factor);
      const [centreRow, maskedRow, shortRow] = [CENTRE, masked, short].map(
        (cell) => DISK.indexOf(cell),
      );
      expect(heights(maskedRow), 'masked rows have no height').toBe(0);
      const shortTop = heights(shortRow) * factor;
      const tallTop = heights(centreRow) * factor;

      // The masked cell's own flat support surface resolves to it.
      expect(resolve(lifted(cellToLatLng(masked), 0))).toBe(maskedRow);
      expect(resolve(lifted(besideEdge(masked, CENTRE), 0))).toBe(maskedRow);
      // The tall centre's wall standing over the masked cell.
      expect(resolve(lifted(besideEdge(masked, CENTRE), tallTop / 2))).toBe(
        centreRow,
      );

      // Over the short cell beside the masked one, above the short top: the
      // masked cell is the nearest neighbour but too low, as is the other
      // short ring cell, so the tall centre wins.
      const overShort = besideEdge(short, masked);
      expect(
        chord(overShort, cellToLatLng(masked)),
        'precondition: the masked cell is the nearest neighbour',
      ).toBeLessThan(chord(overShort, cellToLatLng(CENTRE)));
      expect(resolve(lifted(overShort, (shortTop + tallTop) / 2))).toBe(
        centreRow,
      );
      // Above every top no neighbour qualifies and the projected row stands.
      expect(resolve(lifted(overShort, tallTop + 10_000))).toBe(shortRow);
    },
  );

  it.each([1, 5])(
    'gives boundary wall hits that project off the grid to the grid cell at exaggeration %d',
    (factor) => {
      const { surface, heights } = setup('extruded');
      const resolve = extrudedPick(surface, heights, factor);
      const tallTop = heights(DISK.indexOf(CENTRE)) * factor;
      let walls = 0;
      for (const cell of DISK.filter((h3) => h3 !== CENTRE)) {
        const row = DISK.indexOf(cell);
        for (const outside of gridDisk(cell, 1)) {
          if (DISK.includes(outside)) continue;
          // Just across the grid cell's outer wall, inside the off-grid cell.
          const ground = besideEdge(outside, cell);
          expect(
            resolve(lifted(ground, (heights(row) * factor) / 2)),
            `${cell} outer wall toward ${outside}`,
          ).toBe(row);
          expect(
            resolve(lifted(ground, tallTop + 10_000)),
            `${outside} above every top`,
          ).toBeNull();
          walls += 1;
        }
      }
      expect(walls).toBe(18);
    },
  );

  it('breaks an exact centre-distance tie toward the lower row', async () => {
    const { cellToLatLng: realCellToLatLng } =
      await vi.importActual<typeof import('h3-js')>('h3-js');
    const tall = [DISK[2], DISK[4], DISK[6]];
    const { surface, heights } = setup('extruded', CENTRE, (h3) => ({
      support: 'interpolated',
      value: tall.includes(h3) ? TALL : h3 === CENTRE ? 0.1 : SHORT,
    }));
    const visited = gridDisk(CENTRE, 1)
      .filter((cell) => tall.includes(cell))
      .map((cell) => DISK.indexOf(cell));
    const lowest = Math.min(...visited);
    // Preconditions: the centre is not tied, and the lowest tied row is
    // neither the first nor the last that gridDisk visits, so neither
    // "first wins" nor "last wins" passes.
    expect(tall).not.toContain(CENTRE);
    expect(visited[0]).not.toBe(lowest);
    expect(visited.at(-1)).not.toBe(lowest);
    // Above the centre and the short ring, below the tall ring.
    const point = lifted(realCellToLatLng(CENTRE), 100_000);
    const spy = vi.mocked(cellToLatLng);
    spy.mockImplementation(() => [10, 20]);
    try {
      expect(extrudedPick(surface, heights, 1)(point)).toBe(lowest);
    } finally {
      spy.mockImplementation(realCellToLatLng);
    }
  });
});
