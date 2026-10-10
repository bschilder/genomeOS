/** Small MeshInput builders for the fast-load geometry tests (spec §B.8). */

import { SUPPORT_CODES } from '../../src/atlas/gosa/decode';
import type { ChunkPlan, PlannedChunk } from '../../src/atlas/geometry/chunks';
import { planChunks } from '../../src/atlas/geometry/chunks';
import type { MeshInput } from '../../src/atlas/geometry/surface-buffers';
import { buildGridTopology } from '../../src/atlas/geometry/topology';
import type { Support } from '../../src/atlas/contracts';
import type { SurfaceGeometry } from '../../src/atlas/url-state';
import type { PaletteId } from '../../src/atlas/visual-encoding';
import { decodedGridFromH3 } from './atlas-geometry';

export { sortedU64 } from './atlas-geometry';

export interface TestCell {
  h3: string;
  support: Support;
  value: number;
}

/** Cells must be listed in ascending u64 order. */
export function meshInputFor(
  cells: readonly TestCell[],
  options: {
    geometry?: SurfaceGeometry;
    palette?: PaletteId;
    domain?: readonly [number, number];
  } = {},
): MeshInput {
  const grid = decodedGridFromH3(cells.map((cell) => cell.h3));
  return {
    domain: options.domain ?? [0, 1],
    geometry: options.geometry ?? 'triangles',
    grid,
    palette: options.palette ?? 'rainbow',
    support: Uint8Array.from(cells, (cell) =>
      SUPPORT_CODES.indexOf(cell.support),
    ),
    topology: buildGridTopology(grid),
    values: Float32Array.from(cells, (cell) => cell.value),
  };
}

/** One chunk holding every row, for tests that do not exercise the plan. */
export function wholeGridChunk(input: MeshInput): PlannedChunk {
  return {
    centroid: { lat: 0, lon: 0 },
    id: 0,
    rows: Uint32Array.from({ length: input.grid.n }, (_, row) => row),
    seam: false,
  };
}

export function planFor(input: MeshInput): ChunkPlan {
  return planChunks(input.grid, input.topology);
}

export function maxIndex(indices: ArrayLike<number>): number {
  let max = 0;
  for (let index = 0; index < indices.length; index += 1)
    if (indices[index] > max) max = indices[index];
  return max;
}
