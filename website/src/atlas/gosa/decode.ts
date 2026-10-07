/**
 * GOSA v1 tier decoders with every hard error and the cross-tier binding, for Atlas design §11 and
 * fast-load design §B.2–§B.3. Pure and Cesium-free: the data worker and vitest call it directly.
 * Order (interface contract, "GOSA error codes"): declared digest, container structure, tier
 * values, then catalog context.
 */

import { getResolution, splitLongToH3Index } from 'h3-js';

import type { GridEntry } from '../contracts';
import { fail, parseContainer, unshuffle } from './container';
import { sha256Hex } from './sha256';
import type { DecodedGrid } from './types';

export {
  FORMAT_VERSION,
  GOSA_ERROR_CODES,
  GosaError,
  type GosaErrorCode,
  type GosaTier,
} from './container';

/** Receives each phase in `performance.now()` milliseconds of the calling realm. */
export type DecodeTiming = (
  phase: 'decode' | 'verify',
  start: number,
  end: number,
) => void;

export interface DeclaredObject {
  bytes: number;
  sha256: string;
}

function timed<T>(
  timing: DecodeTiming | undefined,
  phase: 'decode' | 'verify',
  run: () => T,
): T {
  const start = performance.now();
  try {
    return run();
  } finally {
    timing?.(phase, start, performance.now());
  }
}

/** Check 0: the container's decoded size and SHA-256 must equal the catalog declaration. */
export function verifyContainer(
  bytes: Uint8Array,
  declared: DeclaredObject,
  label: string,
): void {
  if (bytes.byteLength !== declared.bytes) {
    fail(
      'container_sha256',
      `${label} is ${bytes.byteLength} bytes; the catalog declares ${declared.bytes}`,
    );
  }
  const digest = sha256Hex(bytes);
  if (digest !== declared.sha256) {
    fail(
      'container_sha256',
      `${label} SHA-256 ${digest} does not match the catalog digest ${declared.sha256}`,
    );
  }
}

type Lanes = Pick<DecodedGrid, 'h3Hi' | 'h3Lo'>;

/** Check 16: delta_shuffle with two u32 lanes and carry; a carry out of the high lane is not increasing. */
function decodeDeltaLanes(encoded: Uint8Array, n: number): Lanes {
  const deltas = new Uint32Array(unshuffle(encoded, 8));
  const h3Lo = new Uint32Array(n);
  const h3Hi = new Uint32Array(n);
  let lo = 0;
  let hi = 0;
  for (let row = 0; row < n; row += 1) {
    const deltaLo = deltas[2 * row];
    const deltaHi = deltas[2 * row + 1];
    if (row === 0) {
      lo = deltaLo;
      hi = deltaHi;
    } else {
      if (deltaLo === 0 && deltaHi === 0) {
        fail(
          'grid_order',
          `grid not strictly increasing at row ${row} (zero delta)`,
        );
      }
      const sum = lo + deltaLo;
      lo = sum >>> 0;
      hi = hi + deltaHi + (sum > 0xffffffff ? 1 : 0);
      if (hi > 0xffffffff) {
        fail(
          'grid_order',
          `grid not strictly increasing at row ${row}: the index passes 2^64`,
        );
      }
    }
    h3Lo[row] = lo;
    h3Hi[row] = hi;
  }
  return { h3Hi, h3Lo };
}

/** Check 17: h3-js `getResolution` returns -1 for an invalid cell, so one call covers both rules. */
function requireCells(lanes: Lanes, resolution: number): void {
  const pair: [number, number] = [0, 0];
  for (let row = 0; row < lanes.h3Lo.length; row += 1) {
    pair[0] = lanes.h3Lo[row];
    pair[1] = lanes.h3Hi[row];
    if (getResolution(pair) !== resolution) {
      fail(
        'h3_cell',
        `Grid row ${row} (${splitLongToH3Index(pair[0], pair[1])}) is not a valid resolution-${resolution} H3 cell`,
      );
    }
  }
}

/** SHA-256 of the decoded little-endian u64 column (n × 8 bytes). */
function gridDigest(lanes: Lanes): string {
  const bytes = new Uint8Array(lanes.h3Lo.length * 8);
  const view = new DataView(bytes.buffer);
  for (let row = 0; row < lanes.h3Lo.length; row += 1) {
    view.setUint32(8 * row, lanes.h3Lo[row], true);
    view.setUint32(8 * row + 4, lanes.h3Hi[row], true);
  }
  return sha256Hex(bytes);
}

export function decodeGrid(
  buf: ArrayBuffer,
  expect: { entry: GridEntry; gridSha256: string },
  timing?: DecodeTiming,
): DecodedGrid {
  const { entry, gridSha256 } = expect;
  const bytes = new Uint8Array(buf);
  const label = `Grid ${entry.url}`;
  timed(timing, 'verify', () => verifyContainer(bytes, entry, label));
  return timed(timing, 'decode', () => {
    const { columns, header } = parseContainer(bytes, 'grid');
    const lanes = decodeDeltaLanes(columns[0], header.n_cells);
    requireCells(lanes, header.resolution);
    const digest = gridDigest(lanes);
    if (digest !== header.grid_sha256) {
      fail(
        'grid_sha256',
        `${label} cells hash to ${digest}; the header declares ${header.grid_sha256}`,
      );
    }
    if (digest !== gridSha256) {
      fail(
        'grid_sha256',
        `${label} cells hash to ${digest}; the catalog key is ${gridSha256}`,
      );
    }
    if (header.n_cells !== entry.n_cells) {
      fail(
        'n_cells',
        `${label} has ${header.n_cells} cells; the catalog declares ${entry.n_cells}`,
      );
    }
    // The only TS-only check: Python decodes a grid without a catalog entry.
    if (header.resolution !== entry.resolution) {
      fail(
        'header_schema',
        `${label} resolution ${header.resolution} does not match the catalog resolution ${entry.resolution}`,
      );
    }
    return {
      gridSha256: digest,
      h3Hi: lanes.h3Hi,
      h3Lo: lanes.h3Lo,
      n: header.n_cells,
      resolution: header.resolution,
    };
  });
}
