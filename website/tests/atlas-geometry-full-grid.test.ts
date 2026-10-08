import { cellToBoundary } from 'h3-js';
import { describe, expect, it } from 'vitest';

import { planChunks, type ChunkPlan } from '../src/atlas/geometry/chunks';
import { crossesAntimeridian } from '../src/atlas/geometry/polygon-parts';
import {
  buildSurfaceChunk,
  type MeshInput,
  type SurfaceChunkBuffers,
} from '../src/atlas/geometry/surface-buffers';
import { buildSupportChunk } from '../src/atlas/geometry/support-buffers';
import {
  buildGridTopology,
  type GridTopology,
} from '../src/atlas/geometry/topology';
import { needsLongitudeSplit } from '../src/atlas/geometry/wgs84';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import {
  CYT_FULL_GRID_SURFACE,
  FULL_GRID_SURFACE,
  hasFullGrid,
  publishedSurfaces,
  surfaceFixture,
  type SurfaceFixture,
} from './helpers/atlas-geometry';
import { maxIndex } from './helpers/mesh-input';

const MAX_BOUNDING_RADIUS_METRES = 2_500_000;
/** HbS surface primitives that skip Cesium's splitLongitude early exit
 * (spec B.8 "at most two chunks of the default artifact"; measured: chunks 2 and 85). */
const MAX_SURFACE_LONGITUDE_SPLITS = 2;
/** The catalog's first artifact, whose cold load the §B.1 budgets govern. */
const DEFAULT_ARTIFACT = 'hbs-rs334';
/** §B.8's bound on the default artifact's surface chunks that fail the splitLongitude early-out
 * (Plan ruling R19, controller ruling R19-b). Support primitives may fail it and are not counted;
 * seam chunks are counted. */
const MAX_CHUNKS_FAILING_SPLIT = 2;
/** Each artifact's surface chunks that fail the splitLongitude early-out, as measured on the shared
 * chunk plan (§B.8, R19-b), pinned as upper bounds so a chunk-plan change that raises any count
 * fails. The plan is shared, so the counts differ only by which chunks along ±180° hold an
 * artifact's supported cells: HbS's cells there are `unknown` (support primitives, not counted),
 * while the HLA and KIR layers support nearly all of theirs. */
const MEASURED_SURFACE_SPLITS: Readonly<Record<string, number>> = {
  'cyt-il-10-1082-g': 6,
  'cyt-il-10-819-t': 6,
  'cyt-il-6-174-c': 1,
  'cyt-tnfalpha-308-a': 1,
  'g6pd-deficiency': 4,
  'hbs-rs334': 2,
  'hla-a-02-01': 12,
  'hla-a-26-01': 13,
  'hla-a-32-01': 12,
  'hla-b-40-01': 12,
  'hla-b-40-02': 12,
  'hla-b-58-01': 12,
  'hla-c-03-03': 12,
  'hla-c-06-02': 11,
  'hla-c-07-02': 10,
  'hla-dpb1-04-01': 12,
  'hla-dpb1-04-02': 11,
  'hla-dpb1-13-01': 11,
  'hla-dqb1-03-01': 13,
  'hla-dqb1-06-02': 12,
  'hla-drb1-01-01': 12,
  'hla-drb1-04-03': 12,
  'hla-drb1-07-01': 12,
  'hla-drb1-11-01': 12,
  'hla-drb1-14-01': 12,
  'hla-drb1-15-01': 12,
  'kir-2dl1': 7,
  'kir-2dl2': 12,
  'kir-2ds1': 12,
  'kir-3ds1': 12,
};

function inputFor(
  fixture: SurfaceFixture,
  topology: GridTopology,
  geometry: SurfaceGeometry,
): MeshInput {
  return {
    domain: fixture.artifact.metric_domains.post_mean,
    geometry,
    grid: fixture.grid,
    palette: 'rainbow',
    support: fixture.support,
    topology,
    values: fixture.post_mean,
  };
}

function crossesSeam(buffers: SurfaceChunkBuffers, triangle: number): boolean {
  const lon = [0, 1, 2].map((corner) => {
    const vertex = buffers.indices[triangle * 3 + corner];
    return Math.atan2(
      buffers.positions[vertex * 3 + 1],
      buffers.positions[vertex * 3],
    );
  });
  return Math.max(...lon) - Math.min(...lon) > Math.PI;
}

describe.skipIf(!hasFullGrid)(
  'chunk rule on the full 77,844-cell grid (fast-load §B.8)',
  () => {
    const hbs = hasFullGrid ? surfaceFixture(FULL_GRID_SURFACE!) : null;
    const topology = hbs ? buildGridTopology(hbs.grid) : null;
    const plan: ChunkPlan | null =
      hbs && topology ? planChunks(hbs.grid, topology) : null;

    it('puts every supported and masked cell in exactly one chunk', () => {
      const seen = new Uint8Array(hbs!.grid.n);
      for (const chunk of plan!.chunks)
        for (const row of chunk.rows) seen[row] += 1;
      expect(seen.every((count) => count === 1)).toBe(true);
      for (const chunk of plan!.chunks)
        for (const row of chunk.rows)
          expect(
            crossesAntimeridian([hbs!.grid.h3Lo[row], hbs!.grid.h3Hi[row]]),
          ).toBe(chunk.seam);
    });

    it.each(['triangles', 'extruded'] as const)(
      'keeps %s chunks within 2,500 km, their index type and the seam',
      (geometry) => {
        const input = inputFor(hbs!, topology!, geometry);
        let splits = 0;
        for (const chunk of plan!.chunks) {
          const buffers = buildSurfaceChunk(input, chunk);
          expect(
            buffers.boundingSphere.radius,
            `chunk ${chunk.id}`,
          ).toBeLessThanOrEqual(MAX_BOUNDING_RADIUS_METRES);
          const vertices = buffers.heights.length;
          expect(buffers.indices instanceof Uint32Array).toBe(
            vertices > 65_535,
          );
          expect(maxIndex(buffers.indices)).toBeLessThan(Math.max(vertices, 1));
          if (!chunk.seam)
            for (
              let triangle = 0;
              triangle < buffers.indices.length / 3;
              triangle += 1
            )
              expect(
                crossesSeam(buffers, triangle),
                `chunk ${chunk.id} triangle ${triangle}`,
              ).toBe(false);
          if (needsLongitudeSplit(buffers.boundingSphere)) splits += 1;
        }
        expect(splits).toBeLessThanOrEqual(MAX_SURFACE_LONGITUDE_SPLITS);
      },
      120_000,
    );

    it('covers exactly each chunk masked cells with its support buffers', () => {
      const cyt = surfaceFixture(CYT_FULL_GRID_SURFACE!);
      const input = inputFor(cyt, topology!, 'triangles');
      const covered = { prior: 0, unknown: 0 };
      for (const chunk of plan!.chunks) {
        const support = buildSupportChunk(input, chunk);
        const vertices = (support: string) =>
          [...chunk.rows]
            .filter((row) => cyt.cells[row].support === support)
            .reduce(
              (total, row) =>
                total + cellToBoundary(cyt.cells[row].h3_index).length + 1,
              0,
            );
        expect(support.unknown ? support.unknown.positions.length / 3 : 0).toBe(
          vertices('unknown'),
        );
        expect(
          support.priorDominated.reduce(
            (total, bin) => total + bin.buffers.positions.length / 3,
            0,
          ),
        ).toBe(vertices('prior_dominated'));
        covered.unknown += [...chunk.rows].filter(
          (row) => cyt.cells[row].support === 'unknown',
        ).length;
        covered.prior += [...chunk.rows].filter(
          (row) => cyt.cells[row].support === 'prior_dominated',
        ).length;
      }
      expect(covered).toEqual({ prior: 3_307, unknown: 7_355 });
    }, 120_000);

    it('keeps every artifact within its splitLongitude early-out bound (§B.8, R19)', () => {
      const counts: {
        either: number;
        id: string;
        support: number;
        surface: number;
      }[] = [];
      for (const { id, path } of publishedSurfaces()) {
        const fixture = surfaceFixture(path);
        expect(
          fixture.grid.n === hbs!.grid.n &&
            fixture.grid.h3Lo.every(
              (low, row) =>
                low === hbs!.grid.h3Lo[row] &&
                fixture.grid.h3Hi[row] === hbs!.grid.h3Hi[row],
            ),
          `${id} is on the shared grid`,
        ).toBe(true);
        // The chunk plan is shared, but surface and support buffers depend on each
        // artifact's own support pattern, so §B.8's "per artifact" is checked per artifact,
        // in the default layer's geometry (`triangles`).
        const input = inputFor(fixture, topology!, 'triangles');
        const count = { either: 0, id, support: 0, surface: 0 };
        for (const chunk of plan!.chunks) {
          const surfaceFails = needsLongitudeSplit(
            buildSurfaceChunk(input, chunk).boundingSphere,
          );
          const support = buildSupportChunk(input, chunk);
          const supportFails = [
            support.unknown,
            ...support.priorDominated.map(({ buffers }) => buffers),
          ].some(
            (buffers) =>
              buffers !== null && needsLongitudeSplit(buffers.boundingSphere),
          );
          if (surfaceFails) count.surface += 1;
          if (supportFails) count.support += 1;
          if (surfaceFails || supportFails) count.either += 1;
        }
        counts.push(count);
      }
      // Per-artifact chunks failing the early-out, surface and support separately, for the
      // Part B PR notes (R19).
      console.table(counts);
      expect(counts).toHaveLength(30);
      expect(counts[0].id, 'the default artifact').toBe(DEFAULT_ARTIFACT);
      expect(
        counts[0].surface,
        `${DEFAULT_ARTIFACT}: surface chunks failing the splitLongitude early-out`,
      ).toBeLessThanOrEqual(MAX_CHUNKS_FAILING_SPLIT);
      expect(counts.map(({ id }) => id).sort()).toEqual(
        Object.keys(MEASURED_SURFACE_SPLITS).sort(),
      );
      expect(
        counts
          .filter(({ id, surface }) => surface > MEASURED_SURFACE_SPLITS[id])
          .map(
            ({ id, surface }) =>
              `${id}: ${surface} > ${MEASURED_SURFACE_SPLITS[id]}`,
          ),
        'surface chunks failing the splitLongitude early-out, above the measured pin',
      ).toEqual([]);
    }, 600_000);
  },
);
