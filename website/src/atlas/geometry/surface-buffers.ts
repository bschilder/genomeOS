/** Worker-built surface chunk buffers (fast-load spec 2026-10-07 §B.6.5).
 *
 * `triangles`/`honmoon`/`honmoon-fill` share one vertex per H3 corner within a
 * chunk; `hexagons`/`extruded` emit per-cell flat geometry carrying the
 * palette-bin colour. Vertex means are summed in float64 over adjacent
 * supported cells in grid order and stored as float32, like the legacy
 * attributes. Positions sit at SURFACE_CLEARANCE_METRES; the shader raises
 * them along `elevationNormals`. Presentation only: no value is invented.
 */

import type { SurfaceGeometry } from '../url-state';
import {
  colorBytesAtStops,
  heightFor,
  linearStops,
  normalizedValue,
  quantizeMetric,
  type MetricDomain,
  type PaletteId,
} from '../visual-encoding';
import type { DecodedGrid } from '../gosa/types';
import type { PlannedChunk } from './chunks';
import {
  isSupportedCode,
  PRIOR_DOMINATED_CODE,
  supportName,
} from './support-codes';
import type { GridTopology } from './topology';
import {
  boundingSphereOf,
  geodeticToEcef,
  normalizeInto,
  type BoundingSphere,
} from './wgs84';

export const SURFACE_CLEARANCE_METRES = 650;
export const CPU_EXTRUSION_EPSILON_METRES = 1;
/** Upper end of the URL exaggeration range (`url-state.ts`, [0.25, 5]). */
export const MAX_ELEVATION_FACTOR = 5;
const UINT16_VERTEX_LIMIT = 65_535;

export interface MeshInput {
  grid: DecodedGrid;
  topology: GridTopology;
  support: Uint8Array;
  /** The displayed metric's render-tier column, positional on `grid`. */
  values: Float32Array;
  domain: MetricDomain;
  palette: PaletteId;
  geometry: SurfaceGeometry;
  /** Optional override; when present it must equal `vertexMeans(input).heights`. */
  vertexHeights?: Float32Array;
}

export interface SurfaceChunkBuffers {
  chunk: number;
  positions: Float64Array;
  normals: Float32Array;
  elevationNormals: Float32Array;
  colors: Float32Array;
  heights: Float32Array;
  values: Float32Array;
  indices: Uint16Array | Uint32Array;
  boundingSphere: BoundingSphere;
}

export interface VertexMeans {
  /** Mean adjacent supported-cell height at exaggeration 1, per topology vertex. */
  heights: Float32Array;
  /** Normalised position of the mean adjacent supported value, per vertex. */
  values: Float32Array;
}

export interface PaletteBins {
  /** Bin of each grid row in the selected support set; -1 elsewhere. */
  binOfRow: Int8Array;
  /** sRGB bytes of each bin: the colour of its first row in grid order. */
  colors: Map<number, [number, number, number]>;
}

export function isSmoothGeometry(geometry: SurfaceGeometry): boolean {
  return (
    geometry === 'triangles' ||
    geometry === 'honmoon' ||
    geometry === 'honmoon-fill'
  );
}

interface MeansEntry {
  topology: GridTopology;
  support: Uint8Array;
  lower: number;
  upper: number;
  means: VertexMeans;
}

const meansCache = new WeakMap<Float32Array, MeansEntry[]>();

export function vertexMeans(input: MeshInput): VertexMeans {
  const entries = meansCache.get(input.values) ?? [];
  const cached = entries.find(
    (entry) =>
      entry.topology === input.topology &&
      entry.support === input.support &&
      entry.lower === input.domain[0] &&
      entry.upper === input.domain[1],
  );
  if (cached) return cached.means;
  const { topology, support, values, domain } = input;
  const vertexCount = topology.vertexLat.length;
  const heightSums = new Float64Array(vertexCount);
  const valueSums = new Float64Array(vertexCount);
  const counts = new Uint8Array(vertexCount);
  for (let row = 0; row < topology.n; row += 1) {
    const code = support[row];
    if (!isSupportedCode(code)) continue;
    const value = values[row];
    const height = heightFor(supportName(code), value, domain, 1);
    for (
      let corner = topology.cornerOffsets[row];
      corner < topology.cornerOffsets[row + 1];
      corner += 1
    ) {
      const id = topology.cornerIds[corner];
      heightSums[id] += height;
      valueSums[id] += value;
      counts[id] += 1;
    }
  }
  const heights = new Float32Array(vertexCount);
  const meanValues = new Float32Array(vertexCount);
  for (let id = 0; id < vertexCount; id += 1) {
    if (counts[id] === 0) continue;
    heights[id] = heightSums[id] / counts[id];
    meanValues[id] = normalizedValue(valueSums[id] / counts[id], domain);
  }
  const means = { heights, values: meanValues };
  entries.push({
    lower: domain[0],
    means,
    support,
    topology,
    upper: domain[1],
  });
  meansCache.set(values, entries);
  return means;
}

const binsCache = new WeakMap<
  Float32Array,
  WeakMap<Uint8Array, Map<string, PaletteBins>>
>();

/** `paletteBinsForCells` semantics over the rows whose support is selected. */
export function paletteBins(
  input: Pick<MeshInput, 'support' | 'values' | 'domain' | 'palette'>,
  set: 'supported' | 'prior_dominated',
): PaletteBins {
  const key = `${set}|${input.palette}|${input.domain[0]}|${input.domain[1]}`;
  const bySupport =
    binsCache.get(input.values) ??
    new WeakMap<Uint8Array, Map<string, PaletteBins>>();
  const byKey = bySupport.get(input.support) ?? new Map<string, PaletteBins>();
  const cached = byKey.get(key);
  if (cached) return cached;
  const stops = linearStops(input.palette);
  const binOfRow = new Int8Array(input.support.length).fill(-1);
  const colors = new Map<number, [number, number, number]>();
  for (let row = 0; row < input.support.length; row += 1) {
    const code = input.support[row];
    const selected =
      set === 'supported'
        ? isSupportedCode(code)
        : code === PRIOR_DOMINATED_CODE;
    if (!selected) continue;
    const value = input.values[row];
    const bin = quantizeMetric(value, input.domain);
    binOfRow[row] = bin;
    if (!colors.has(bin))
      colors.set(
        bin,
        colorBytesAtStops(stops, normalizedValue(value, input.domain)),
      );
  }
  const bins = { binOfRow, colors };
  byKey.set(key, bins);
  bySupport.set(input.support, byKey);
  binsCache.set(input.values, bySupport);
  return bins;
}

export function indexArrayFor(
  vertexCount: number,
  indices: ArrayLike<number>,
): Uint16Array | Uint32Array {
  return vertexCount > UINT16_VERTEX_LIMIT
    ? Uint32Array.from(indices)
    : Uint16Array.from(indices);
}

/** Sphere over every vertex at rest and fully raised (exaggeration 5). */
export function elevatedBoundingSphere(
  positions: Float64Array,
  elevationNormals: Float32Array,
  heights: Float32Array,
): BoundingSphere {
  const raised = new Float64Array(positions.length);
  for (let vertex = 0; vertex < heights.length; vertex += 1) {
    const lift = heights[vertex] * MAX_ELEVATION_FACTOR;
    for (let axis = 0; axis < 3; axis += 1)
      raised[vertex * 3 + axis] =
        positions[vertex * 3 + axis] +
        elevationNormals[vertex * 3 + axis] * lift;
  }
  return boundingSphereOf([positions, raised]);
}

class VertexWriter {
  readonly positions: Float64Array;
  readonly normals: Float32Array;
  readonly elevationNormals: Float32Array;
  readonly colors: Float32Array;
  readonly heights: Float32Array;
  readonly values: Float32Array;
  count = 0;
  readonly #scratch = new Float64Array(3);

  constructor(vertexCount: number, separateElevationNormals: boolean) {
    this.positions = new Float64Array(vertexCount * 3);
    this.normals = new Float32Array(vertexCount * 3);
    this.elevationNormals = separateElevationNormals
      ? new Float32Array(vertexCount * 3)
      : this.normals;
    this.colors = new Float32Array(vertexCount * 3);
    this.heights = new Float32Array(vertexCount);
    this.values = new Float32Array(vertexCount);
  }

  /** Appends a vertex; `shading` defaults to the geocentric position normal. */
  add(
    position: ArrayLike<number>,
    height: number,
    value: number,
    color: readonly [number, number, number],
    shading?: ArrayLike<number>,
  ): number {
    const vertex = this.count;
    const offset = vertex * 3;
    this.positions[offset] = position[0];
    this.positions[offset + 1] = position[1];
    this.positions[offset + 2] = position[2];
    normalizeInto(position, 0, this.#scratch);
    for (let axis = 0; axis < 3; axis += 1) {
      this.elevationNormals[offset + axis] = this.#scratch[axis];
      if (shading) this.normals[offset + axis] = shading[axis];
      this.colors[offset + axis] = color[axis] / 255;
    }
    this.heights[vertex] = height;
    this.values[vertex] = value;
    this.count += 1;
    return vertex;
  }
}

function supportedRows(input: MeshInput, chunk: PlannedChunk): number[] {
  const rows: number[] = [];
  for (const row of chunk.rows)
    if (isSupportedCode(input.support[row])) rows.push(row);
  return rows;
}

function cornerCount(topology: GridTopology, row: number): number {
  return topology.cornerOffsets[row + 1] - topology.cornerOffsets[row];
}

function buildSmoothChunk(
  input: MeshInput,
  chunk: PlannedChunk,
  rows: readonly number[],
): SurfaceChunkBuffers {
  const { topology, domain } = input;
  const means = vertexMeans(input);
  const heights = input.vertexHeights ?? means.heights;
  const stops = linearStops(input.palette);
  const local = new Map<number, number>();
  let vertexCount = 0;
  let triangleCount = 0;
  for (const row of rows) {
    vertexCount += 1;
    triangleCount += cornerCount(topology, row);
    for (
      let corner = topology.cornerOffsets[row];
      corner < topology.cornerOffsets[row + 1];
      corner += 1
    ) {
      const id = topology.cornerIds[corner];
      if (!local.has(id)) {
        local.set(id, -1);
        vertexCount += 1;
      }
    }
  }
  local.clear();
  const writer = new VertexWriter(vertexCount, false);
  const indices = new Array<number>(triangleCount * 3);
  const position = new Float64Array(3);
  let next = 0;
  for (const row of rows) {
    const value = input.values[row];
    const t = normalizedValue(value, domain);
    geodeticToEcef(
      topology.centreLon[row],
      topology.centreLat[row],
      SURFACE_CLEARANCE_METRES,
      position,
    );
    const centre = writer.add(
      position,
      heightFor(supportName(input.support[row]), value, domain, 1),
      t,
      colorBytesAtStops(stops, t),
    );
    const first = topology.cornerOffsets[row];
    const count = cornerCount(topology, row);
    const ring: number[] = [];
    for (let corner = 0; corner < count; corner += 1) {
      const id = topology.cornerIds[first + corner];
      let vertex = local.get(id);
      if (vertex === undefined) {
        geodeticToEcef(
          topology.vertexLon[id],
          topology.vertexLat[id],
          SURFACE_CLEARANCE_METRES,
          position,
        );
        vertex = writer.add(
          position,
          heights[id],
          means.values[id],
          colorBytesAtStops(stops, means.values[id]),
        );
        local.set(id, vertex);
      }
      ring.push(vertex);
    }
    for (let corner = 0; corner < count; corner += 1) {
      indices[next++] = centre;
      indices[next++] = ring[corner];
      indices[next++] = ring[(corner + 1) % count];
    }
  }
  return finish(chunk, writer, indices);
}

function cpuTop(ground: Float64Array, out: Float64Array): void {
  const normal = new Float64Array(3);
  normalizeInto(ground, 0, normal);
  out[0] = ground[0] + normal[0] * CPU_EXTRUSION_EPSILON_METRES;
  out[1] = ground[1] + normal[1] * CPU_EXTRUSION_EPSILON_METRES;
  out[2] = ground[2] + normal[2] * CPU_EXTRUSION_EPSILON_METRES;
}

function sideNormal(
  first: Float64Array,
  second: Float64Array,
  center: Float64Array,
): Float64Array {
  const edge = [
    second[0] - first[0],
    second[1] - first[1],
    second[2] - first[2],
  ];
  const sum = [
    first[0] + second[0],
    first[1] + second[1],
    first[2] + second[2],
  ];
  const radial = new Float64Array(3);
  normalizeInto(sum, 0, radial);
  const cross = [
    edge[1] * radial[2] - edge[2] * radial[1],
    edge[2] * radial[0] - edge[0] * radial[2],
    edge[0] * radial[1] - edge[1] * radial[0],
  ];
  const normal = new Float64Array(3);
  normalizeInto(cross, 0, normal);
  const midpoint = [sum[0] * 0.5, sum[1] * 0.5, sum[2] * 0.5];
  const outward = [
    midpoint[0] - center[0],
    midpoint[1] - center[1],
    midpoint[2] - center[2],
  ];
  if (
    normal[0] * outward[0] + normal[1] * outward[1] + normal[2] * outward[2] <
    0
  ) {
    normal[0] = -normal[0];
    normal[1] = -normal[1];
    normal[2] = -normal[2];
  }
  return normal;
}

function buildFlatChunk(
  input: MeshInput,
  chunk: PlannedChunk,
  rows: readonly number[],
  extruded: boolean,
): SurfaceChunkBuffers {
  const { topology, domain } = input;
  const bins = paletteBins(input, 'supported');
  let vertexCount = 0;
  let indexCount = 0;
  for (const row of rows) {
    const count = cornerCount(topology, row);
    vertexCount += 1 + count + (extruded ? count * 4 : 0);
    indexCount += count * 3 + (extruded ? count * 6 : 0);
  }
  const writer = new VertexWriter(vertexCount, true);
  const indices = new Array<number>(indexCount);
  let next = 0;
  const center = new Float64Array(3);
  const top = new Float64Array(3);
  const shading = new Float64Array(3);
  for (const row of rows) {
    const value = input.values[row];
    const t = normalizedValue(value, domain);
    const height = heightFor(supportName(input.support[row]), value, domain, 1);
    const color = bins.colors.get(bins.binOfRow[row])!;
    const count = cornerCount(topology, row);
    const first = topology.cornerOffsets[row];
    geodeticToEcef(
      topology.centreLon[row],
      topology.centreLat[row],
      SURFACE_CLEARANCE_METRES,
      center,
    );
    const grounds = Array.from({ length: count }, (_, corner) => {
      const id = topology.cornerIds[first + corner];
      const ground = new Float64Array(3);
      geodeticToEcef(
        topology.vertexLon[id],
        topology.vertexLat[id],
        SURFACE_CLEARANCE_METRES,
        ground,
      );
      return ground;
    });
    normalizeInto(center, 0, shading);
    if (extruded) cpuTop(center, top);
    const topCenter = writer.add(
      extruded ? top : center,
      height,
      t,
      color,
      shading,
    );
    const topCorners = grounds.map((ground) => {
      const shadingNormal = new Float64Array(3);
      normalizeInto(ground, 0, shadingNormal);
      if (!extruded) return writer.add(ground, height, t, color, shadingNormal);
      const raised = new Float64Array(3);
      cpuTop(ground, raised);
      return writer.add(raised, height, t, color, shadingNormal);
    });
    for (let corner = 0; corner < count; corner += 1) {
      indices[next++] = topCenter;
      indices[next++] = topCorners[corner];
      indices[next++] = topCorners[(corner + 1) % count];
    }
    for (let corner = 0; extruded && corner < count; corner += 1) {
      const firstGround = grounds[corner];
      const secondGround = grounds[(corner + 1) % count];
      const normal = sideNormal(firstGround, secondGround, center);
      const firstTop = new Float64Array(3);
      const secondTop = new Float64Array(3);
      cpuTop(firstGround, firstTop);
      cpuTop(secondGround, secondTop);
      const bottomFirst = writer.add(firstGround, 0, t, color, normal);
      const bottomSecond = writer.add(secondGround, 0, t, color, normal);
      const topFirst = writer.add(firstTop, height, t, color, normal);
      const topSecond = writer.add(secondTop, height, t, color, normal);
      indices[next++] = bottomFirst;
      indices[next++] = bottomSecond;
      indices[next++] = topSecond;
      indices[next++] = bottomFirst;
      indices[next++] = topSecond;
      indices[next++] = topFirst;
    }
  }
  return finish(chunk, writer, indices);
}

function finish(
  chunk: PlannedChunk,
  writer: VertexWriter,
  indices: number[],
): SurfaceChunkBuffers {
  return {
    boundingSphere: elevatedBoundingSphere(
      writer.positions,
      writer.elevationNormals,
      writer.heights,
    ),
    chunk: chunk.id,
    colors: writer.colors,
    elevationNormals: writer.elevationNormals,
    heights: writer.heights,
    indices: indexArrayFor(writer.count, indices),
    normals: writer.normals,
    positions: writer.positions,
    values: writer.values,
  };
}

/** Surface buffers for the chunk's supported rows (empty arrays when none). */
export function buildSurfaceChunk(
  input: MeshInput,
  chunk: PlannedChunk,
): SurfaceChunkBuffers {
  const rows = supportedRows(input, chunk);
  if (isSmoothGeometry(input.geometry))
    return buildSmoothChunk(input, chunk, rows);
  return buildFlatChunk(input, chunk, rows, input.geometry === 'extruded');
}
