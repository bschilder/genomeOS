import { Cartesian3 } from 'cesium';

import type {
  FlatCellBuffers,
  SupportChunkBuffers,
} from '../../src/atlas/geometry/support-buffers';
import type { SurfaceChunkBuffers } from '../../src/atlas/geometry/surface-buffers';
import type {
  ChunkMessage,
  ObservationAnchorBuffers,
} from '../../src/atlas/worker/protocol';

const CLEARANCE_METRES = 650;
const TRIANGLE: readonly (readonly [number, number])[] = [
  [0, 0],
  [0.2, 0],
  [0, 0.2],
];
/** West edge of the seam triangle: it stays east of ±180°, as a seam chunk does. */
const SEAM_WEST_LONGITUDE = 179.7;

function ecef(height = CLEARANCE_METRES, west = 0): Float64Array {
  return Float64Array.from(
    TRIANGLE.flatMap(([lon, lat]) => {
      const position = Cartesian3.fromDegrees(west + lon, lat, height);
      return [position.x, position.y, position.z];
    }),
  );
}

function radial(positions: Float64Array): Float32Array {
  const normals = new Float32Array(positions.length);
  for (let index = 0; index < positions.length; index += 3) {
    const length = Math.hypot(
      positions[index],
      positions[index + 1],
      positions[index + 2],
    );
    normals[index] = positions[index] / length;
    normals[index + 1] = positions[index + 1] / length;
    normals[index + 2] = positions[index + 2] / length;
  }
  return normals;
}

function sphere(west = 0): {
  center: [number, number, number];
  radius: number;
} {
  const center = Cartesian3.fromDegrees(west + 0.066, 0.066, CLEARANCE_METRES);
  return { center: [center.x, center.y, center.z], radius: 30_000 };
}

export function triangleSurfaceBuffers(
  chunk: number,
  colors = Float32Array.of(1, 0, 0, 0, 1, 0, 0, 0, 1),
  west = 0,
): SurfaceChunkBuffers {
  const positions = ecef(CLEARANCE_METRES, west);
  const normals = radial(positions);
  return {
    boundingSphere: sphere(west),
    chunk,
    colors,
    elevationNormals: normals.slice(),
    heights: Float32Array.of(0, 1_000, 2_000),
    indices: Uint32Array.of(0, 1, 2),
    normals,
    positions,
    values: Float32Array.of(0, 0.5, 1),
  };
}

/** A chunk beside ±180° whose sphere misses Cesium's `splitLongitude` early exit. */
export function seamSurfaceBuffers(chunk: number): SurfaceChunkBuffers {
  return triangleSurfaceBuffers(chunk, undefined, SEAM_WEST_LONGITUDE);
}

export function triangleCellBuffers(): FlatCellBuffers {
  const positions = ecef();
  return {
    boundingSphere: sphere(),
    indices: Uint16Array.of(0, 1, 2),
    normals: radial(positions),
    positions,
    st: Float32Array.of(0, 0, 1, 0, 0, 1),
  };
}

export function emptySupport(chunk: number): SupportChunkBuffers {
  return { chunk, priorDominated: [], unknown: null };
}

export function maskedSupport(chunk: number): SupportChunkBuffers {
  return {
    chunk,
    priorDominated: [
      { bin: 16, buffers: triangleCellBuffers(), color: [204, 71, 120] },
    ],
    unknown: triangleCellBuffers(),
  };
}

export function chunkMessage(
  artifactKey: string,
  chunk: number,
  options: {
    anchors?: ObservationAnchorBuffers | null;
    seam?: boolean;
    support?: SupportChunkBuffers;
    total?: number;
  } = {},
): ChunkMessage {
  return {
    anchors: options.anchors ?? null,
    artifactKey,
    chunk,
    id: 1,
    index: chunk,
    seam: options.seam ?? false,
    support: options.support ?? emptySupport(chunk),
    surface: triangleSurfaceBuffers(chunk),
    total: options.total ?? 1,
    type: 'chunk',
  };
}
