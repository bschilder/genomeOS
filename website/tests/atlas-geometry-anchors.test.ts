import { cellToBoundary, cellToLatLng } from 'h3-js';
import { describe, expect, it } from 'vitest';

import { observationAnchors } from '../src/atlas/geometry/anchors';
import type { MeshInput } from '../src/atlas/geometry/surface-buffers';
import { buildGridTopology } from '../src/atlas/geometry/topology';
import {
  observationSurfaceAnchor,
  observationSurfaceContext,
} from '../src/atlas/scene/observation-symbols';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import type { Metric } from '../src/atlas/visual-encoding';
import {
  GOLDEN_DIR,
  PARITY_DIR,
  surfaceFixturesIn,
  type SurfaceFixture,
} from './helpers/atlas-geometry';

/** f32 storage of a mean height ≤ 180 km moves it by at most one f32 ulp. */
const HEIGHT_TOLERANCE_METRES = 2 ** (17 - 23);

/** Centres, points 88% of the way to each boundary point, and one off-grid point. */
function samplePoints(fixture: SurfaceFixture): Float64Array {
  const points: number[] = [];
  for (const cell of fixture.cells.slice(0, 200)) {
    const [lat, lon] = cellToLatLng(cell.h3_index);
    points.push(lon, lat);
    for (const [vertexLat, vertexLon] of cellToBoundary(cell.h3_index))
      if (Math.abs(vertexLon - lon) < 90)
        points.push(
          lon + (vertexLon - lon) * 0.88,
          lat + (vertexLat - lat) * 0.88,
        );
  }
  points.push(-30, -60);
  return Float64Array.from(points);
}

describe('observation anchors from the render tier (fast-load §B.6.5)', () => {
  const fixtures = [
    ...surfaceFixturesIn(GOLDEN_DIR),
    ...surfaceFixturesIn(PARITY_DIR),
  ];
  it.each(
    fixtures.flatMap((fixture) =>
      (['post_mean', 'post_sd'] as const).flatMap((metric) =>
        (['triangles', 'honmoon-fill', 'hexagons', 'extruded'] as const).map(
          (geometry) => [fixture.name, metric, geometry, fixture] as const,
        ),
      ),
    ),
  )(
    '%s %s %s matches observationSurfaceAnchor',
    (_, metric: Metric, geometry: SurfaceGeometry, fixture) => {
      const input: MeshInput = {
        domain: fixture.artifact.metric_domains[metric],
        geometry,
        grid: fixture.grid,
        palette: 'rainbow',
        support: fixture.support,
        topology: buildGridTopology(fixture.grid),
        values: fixture[metric],
      };
      const points = samplePoints(fixture);
      const anchors = observationAnchors(input, points);
      const surface = {
        artifact: fixture.artifact,
        cells: fixture.froundCells,
        schema_version: 1 as const,
      };
      const context = observationSurfaceContext(surface, metric, geometry);
      for (let index = 0; index < points.length / 2; index += 1) {
        const point = { lat: points[index * 2 + 1], lon: points[index * 2] };
        const legacy = observationSurfaceAnchor(
          point,
          surface,
          metric,
          geometry,
          context,
        );
        expect(
          Math.abs(anchors.heights[index] - legacy.height),
        ).toBeLessThanOrEqual(HEIGHT_TOLERANCE_METRES);
        const triangle = anchors.triangles.subarray(index * 9, index * 9 + 9);
        if (!legacy.triangle) {
          expect([...triangle].every(Number.isNaN)).toBe(true);
          continue;
        }
        legacy.triangle.forEach((vertex, corner) => {
          expect(triangle[corner * 3]).toBe(vertex.lat);
          expect(triangle[corner * 3 + 1]).toBe(vertex.lon);
          expect(
            Math.abs(triangle[corner * 3 + 2] - vertex.height),
          ).toBeLessThanOrEqual(HEIGHT_TOLERANCE_METRES);
        });
      }
    },
  );
});
