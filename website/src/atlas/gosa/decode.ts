/**
 * GOSA v1 tier decoders with every hard error and the cross-tier binding, for Atlas design §11 and
 * fast-load design §B.2–§B.3. Pure and Cesium-free: the data worker and vitest call it directly.
 * Order (interface contract, "GOSA error codes"): declared digest, container structure, tier
 * values, then catalog context.
 */

import { getResolution, splitLongToH3Index } from 'h3-js';

import type {
  ArtifactIdentity,
  ArtifactRef,
  GridEntry,
  Support,
} from '../contracts';
import { identityMessage, identityMismatch } from '../identity';
import {
  fail,
  parseContainer,
  unshuffle,
  type GosaHeader,
  type ParsedContainer,
} from './container';
import { sha256Hex } from './sha256';
import type { DecodedDetail, DecodedGrid, DecodedRender } from './types';

/** Support codes 0–3 (fast-load design §B.3), mirroring SUPPORT_CODES in surface_codec.py. */
export const SUPPORT_CODES = [
  'observed',
  'interpolated',
  'prior_dominated',
  'unknown',
] as const satisfies readonly Support[];

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

const PROBABILITY = [0, 1] as const;
const NON_NEGATIVE = [0, Number.POSITIVE_INFINITY] as const;

/** Check 20, rows ascending: a non-finite value, else a value outside [lower, upper], is a hard error. */
function requireValues(
  values: ArrayLike<number>,
  column: string,
  label: string,
  lower: number,
  upper: number,
): void {
  for (let row = 0; row < values.length; row += 1) {
    const value = values[row];
    if (!Number.isFinite(value)) {
      fail('non_finite', `${label} ${column} row ${row} is ${value}`);
    }
    if (value < lower || value > upper) {
      fail(
        'value_range',
        `${label} ${column} row ${row} is ${value}, outside [${lower}, ${upper}]`,
      );
    }
  }
}

function sameDomains(
  left: ArtifactIdentity['metric_domains'],
  right: ArtifactIdentity['metric_domains'],
): boolean {
  return (
    left.post_mean[0] === right.post_mean[0] &&
    left.post_mean[1] === right.post_mean[1] &&
    left.post_sd[0] === right.post_sd[0] &&
    left.post_sd[1] === right.post_sd[1]
  );
}

/** Render and detail headers always carry an identity; parseContainer has validated it (check 10). */
function headerIdentity(
  parsed: ParsedContainer,
  label: string,
): ArtifactIdentity {
  if (parsed.artifact === null) {
    throw new Error(`${label} parsed without an artifact identity`);
  }
  return parsed.artifact;
}

/** Context checks 23–26: the header identity must be exactly the catalog ref's, on the loaded grid. */
function bindArtifact(
  header: GosaHeader,
  artifact: ArtifactIdentity,
  ref: ArtifactRef,
  grid: DecodedGrid,
  label: string,
): void {
  if (header.n_cells !== ref.n_cells || header.n_cells !== grid.n) {
    fail(
      'n_cells',
      `${label} has ${header.n_cells} cells; the catalog declares ${ref.n_cells} and the grid has ${grid.n}`,
    );
  }
  if (
    header.grid_sha256 !== ref.web.grid_sha256 ||
    header.grid_sha256 !== grid.gridSha256
  ) {
    fail(
      'grid_sha256',
      `${label} is bound to grid ${header.grid_sha256}; the catalog names ${ref.web.grid_sha256} and the loaded grid is ${grid.gridSha256}`,
    );
  }
  const mismatch = identityMismatch(ref, artifact);
  if (mismatch) fail('identity', mismatch);
  if (artifact.label !== ref.label) {
    fail('identity', identityMessage('label', ref.label, artifact.label));
  }
  if (!sameDomains(artifact.metric_domains, ref.metric_domains)) {
    fail(
      'identity',
      identityMessage(
        'metric_domains',
        JSON.stringify(ref.metric_domains),
        JSON.stringify(artifact.metric_domains),
      ),
    );
  }
  if (header.resolution !== grid.resolution) {
    fail(
      'identity',
      `${label} resolution ${header.resolution} differs from the loaded grid's ${grid.resolution}`,
    );
  }
  if (header.source_surface_sha256 !== ref.surface_sha256) {
    fail(
      'source_sha256',
      `${label} was encoded from surface ${header.source_surface_sha256}; the catalog surface is ${ref.surface_sha256}`,
    );
  }
}

export function decodeRender(
  buf: ArrayBuffer,
  expect: { grid: DecodedGrid; ref: ArtifactRef },
  timing?: DecodeTiming,
): DecodedRender {
  const { grid, ref } = expect;
  const label = `${ref.id} render tier`;
  const bytes = new Uint8Array(buf);
  timed(timing, 'verify', () => verifyContainer(bytes, ref.web.render, label));
  return timed(timing, 'decode', () => {
    const parsed = parseContainer(bytes, 'render');
    const artifact = headerIdentity(parsed, label);
    const [supportBytes, meanBytes, sdBytes] = parsed.columns;
    const support = supportBytes.slice();
    for (let row = 0; row < support.length; row += 1) {
      if (support[row] >= SUPPORT_CODES.length) {
        fail(
          'support_code',
          `${label} support row ${row} has code ${support[row]}; valid codes are 0–3`,
        );
      }
    }
    const post_mean = new Float32Array(unshuffle(meanBytes, 4));
    const post_sd = new Float32Array(unshuffle(sdBytes, 4));
    requireValues(post_mean, 'post_mean', label, ...PROBABILITY);
    requireValues(post_sd, 'post_sd', label, ...NON_NEGATIVE);
    bindArtifact(parsed.header, artifact, ref, grid, label);
    // Check 27 (render half): an absent state and an explicit 0 both mean zero cells.
    const histogram = [0, 0, 0, 0];
    for (let row = 0; row < support.length; row += 1)
      histogram[support[row]] += 1;
    SUPPORT_CODES.forEach((state, code) => {
      const declared = ref.support_counts[state] ?? 0;
      if (histogram[code] !== declared) {
        fail(
          'cross_tier',
          `${label} has ${histogram[code]} ${state} cells; the catalog declares ${declared}`,
        );
      }
    });
    return { artifact, post_mean, post_sd, support };
  });
}

export function decodeDetail(
  buf: ArrayBuffer,
  expect: { grid: DecodedGrid; ref: ArtifactRef; render: DecodedRender },
  timing?: DecodeTiming,
): DecodedDetail {
  const { grid, ref, render } = expect;
  const label = `${ref.id} detail tier`;
  const bytes = new Uint8Array(buf);
  timed(timing, 'verify', () => verifyContainer(bytes, ref.web.detail, label));
  return timed(timing, 'decode', () => {
    const parsed = parseContainer(bytes, 'detail');
    const artifact = headerIdentity(parsed, label);
    const [
      post_mean,
      post_sd,
      q025,
      q975,
      posterior_contraction,
      dist_nearest_obs_km,
    ] = parsed.columns.map((column) => new Float64Array(unshuffle(column, 8)));
    requireValues(post_mean, 'post_mean', label, ...PROBABILITY);
    requireValues(post_sd, 'post_sd', label, ...NON_NEGATIVE);
    requireValues(q025, 'q025', label, ...PROBABILITY);
    requireValues(q975, 'q975', label, ...PROBABILITY);
    // posterior SD / prior SD: a ratio above one is legitimate (contracts.ts surfaceCellSchema).
    requireValues(
      posterior_contraction,
      'posterior_contraction',
      label,
      ...NON_NEGATIVE,
    );
    requireValues(
      dist_nearest_obs_km,
      'dist_nearest_obs_km',
      label,
      ...NON_NEGATIVE,
    );
    for (let row = 0; row < post_mean.length; row += 1) {
      if (q025[row] > post_mean[row] || post_mean[row] > q975[row]) {
        fail(
          'interval_order',
          `${label} row ${row} breaks q025 ≤ post_mean ≤ q975 (${q025[row]}, ${post_mean[row]}, ${q975[row]})`,
        );
      }
    }
    bindArtifact(parsed.header, artifact, ref, grid, label);
    if (
      render.post_mean.length !== post_mean.length ||
      render.post_sd.length !== post_sd.length
    ) {
      fail(
        'cross_tier',
        `${label} has ${post_mean.length} rows; its render tier has ${render.post_mean.length}`,
      );
    }
    // Check 27 (detail half): float32 bits, so -0 and +0 differ exactly as surface_codec.py's struct.pack does.
    for (let row = 0; row < post_mean.length; row += 1) {
      if (!Object.is(Math.fround(post_mean[row]), render.post_mean[row])) {
        fail(
          'cross_tier',
          `${label} post_mean row ${row} is ${Math.fround(post_mean[row])} in float32; the render tier holds ${render.post_mean[row]}`,
        );
      }
      if (!Object.is(Math.fround(post_sd[row]), render.post_sd[row])) {
        fail(
          'cross_tier',
          `${label} post_sd row ${row} is ${Math.fround(post_sd[row])} in float32; the render tier holds ${render.post_sd[row]}`,
        );
      }
    }
    return {
      dist_nearest_obs_km,
      post_mean,
      post_sd,
      posterior_contraction,
      q025,
      q975,
    };
  });
}
