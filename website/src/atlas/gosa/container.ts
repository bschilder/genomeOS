/**
 * GOSA v1 container layout, strict header schema and byte-plane decoding for Atlas design §11 and
 * fast-load design §B.3. The checks run in the normative order shared with surface_codec.py (see
 * "GOSA error codes" in the interface contract); a container breaking several rules is refused
 * with the first, so both decoders give the shared mutation corpus the same code.
 */

import { z } from 'zod';

import { artifactIdentitySchema, type ArtifactIdentity } from '../contracts';

export type GosaTier = 'detail' | 'grid' | 'render';

/** Hard-error codes in check order; equal to `surface_codec.GOSA_ERROR_CODES` (corpus manifest `codes`). */
export const GOSA_ERROR_CODES = [
  'truncated',
  'magic',
  'format_version',
  'reserved',
  'header_encoding',
  'header_json',
  'header_schema',
  'tier',
  'identity',
  'columns',
  'column_length',
  'offset',
  'trailing_bytes',
  'padding',
  'grid_order',
  'h3_cell',
  'grid_sha256',
  'support_code',
  'non_finite',
  'value_range',
  'interval_order',
  'n_cells',
  'source_sha256',
  'cross_tier',
  'container_sha256',
] as const;

export type GosaErrorCode = (typeof GOSA_ERROR_CODES)[number];

export class GosaError extends Error {
  readonly code: GosaErrorCode;

  constructor(code: GosaErrorCode, message: string) {
    super(`${code}: ${message}`);
    this.name = 'GosaError';
    this.code = code;
  }
}

export function fail(code: GosaErrorCode, message: string): never {
  throw new GosaError(code, message);
}

export const FORMAT_VERSION = 1;
const MAGIC = [0x47, 0x4f, 0x53, 0x41];
const PREAMBLE_BYTES = 12;
const LITTLE_ENDIAN = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;

interface ColumnSpec {
  dtype: 'f32' | 'f64' | 'u64' | 'u8';
  encoding: 'delta_shuffle' | 'raw' | 'shuffle';
  name: string;
}

export const DTYPE_BYTES = { f32: 4, f64: 8, u64: 8, u8: 1 } as const;

/** The normative per-tier column list of fast-load design §B.2, in order. */
export const TIER_COLUMNS: Readonly<Record<GosaTier, readonly ColumnSpec[]>> = {
  detail: [
    'post_mean',
    'post_sd',
    'q025',
    'q975',
    'posterior_contraction',
    'dist_nearest_obs_km',
  ].map((name): ColumnSpec => ({ dtype: 'f64', encoding: 'shuffle', name })),
  grid: [{ dtype: 'u64', encoding: 'delta_shuffle', name: 'h3' }],
  render: [
    { dtype: 'u8', encoding: 'raw', name: 'support' },
    { dtype: 'f32', encoding: 'shuffle', name: 'post_mean' },
    { dtype: 'f32', encoding: 'shuffle', name: 'post_sd' },
  ],
};

const count = z.int().nonnegative();
const digest = z.string().regex(/^[0-9a-f]{64}$/);

/**
 * Check 8 of the contract table. `dtype`, `encoding` and `name` are plain strings so a wrong value
 * is a `columns` error; integers are JSON numbers (`3.0` is 3, a boolean never is).
 */
const headerSchema = z
  .strictObject({
    artifact: z.record(z.string(), z.unknown()).nullable(),
    columns: z.array(
      z.strictObject({
        dtype: z.string(),
        encoding: z.string(),
        length: count,
        name: z.string(),
        offset: count,
      }),
    ),
    grid_sha256: digest,
    n_cells: count,
    resolution: z.int().min(0).max(15),
    schema_version: z.literal(1),
    source_surface_sha256: digest.nullable(),
    tier: z.enum(['detail', 'grid', 'render']),
  })
  .refine(
    (header) =>
      header.tier === 'grid'
        ? header.artifact === null && header.source_surface_sha256 === null
        : header.artifact !== null && header.source_surface_sha256 !== null,
    {
      message:
        'a grid carries a null artifact and source_surface_sha256; render and detail carry both',
    },
  );

export type GosaHeader = z.infer<typeof headerSchema>;

export interface ParsedContainer {
  /** The validated header identity (render and detail); null for a grid. */
  artifact: ArtifactIdentity | null;
  columns: Uint8Array<ArrayBuffer>[];
  header: GosaHeader;
}

// `fatal` refuses invalid UTF-8; the default `ignoreBOM: false` consumes one leading BOM, exactly as
// surface_codec.py strips one before json.loads.
const UTF8 = new TextDecoder('utf-8', { fatal: true });

export function align8(value: number): number {
  return Math.ceil(value / 8) * 8;
}

function headerText(bytes: Uint8Array): string {
  try {
    return UTF8.decode(bytes);
  } catch {
    return fail('header_encoding', 'GOSA header is not valid UTF-8');
  }
}

function headerJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return fail('header_json', 'GOSA header is not valid JSON');
  }
}

function parseHeader(bytes: Uint8Array): GosaHeader {
  const parsed = headerSchema.safeParse(headerJson(headerText(bytes)));
  if (!parsed.success) {
    fail(
      'header_schema',
      `GOSA header fails the v1 schema: ${parsed.error.issues
        .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
        .join('; ')}`,
    );
  }
  return parsed.data;
}

function requireZeros(bytes: Uint8Array, from: number, to: number): void {
  for (let index = from; index < to; index += 1) {
    if (bytes[index] !== 0) {
      fail(
        'padding',
        `GOSA padding byte ${index} is 0x${bytes[index].toString(16).padStart(2, '0')}, not 0x00`,
      );
    }
  }
}

function describeColumns(
  columns: readonly { dtype: string; encoding: string; name: string }[],
): string {
  return columns
    .map(({ dtype, encoding, name }) => `${name}:${dtype}:${encoding}`)
    .join(',');
}

/** Container-intrinsic checks 1–15 of the contract table, in that order. */
export function parseContainer(
  bytes: Uint8Array<ArrayBuffer>,
  tier: GosaTier,
): ParsedContainer {
  if (!LITTLE_ENDIAN) {
    throw new Error('GOSA decoding requires a little-endian platform');
  }
  if (bytes.byteLength < PREAMBLE_BYTES) {
    fail(
      'truncated',
      `GOSA container is ${bytes.byteLength} bytes, shorter than its 12-byte preamble`,
    );
  }
  if (MAGIC.some((value, index) => bytes[index] !== value)) {
    fail('magic', 'Not a GOSA container: the magic bytes are missing');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const version = view.getUint16(4, true);
  if (version !== FORMAT_VERSION) {
    fail(
      'format_version',
      `GOSA format_version is ${version}, expected ${FORMAT_VERSION}`,
    );
  }
  const reserved = view.getUint16(6, true);
  if (reserved !== 0)
    fail('reserved', `GOSA reserved field is ${reserved}, expected 0`);
  const headerEnd = PREAMBLE_BYTES + view.getUint32(8, true);
  if (headerEnd > bytes.byteLength) {
    fail('truncated', 'GOSA header runs past the end of the container');
  }
  const header = parseHeader(bytes.subarray(PREAMBLE_BYTES, headerEnd));
  if (header.tier !== tier) {
    fail(
      'tier',
      `GOSA tier is ${JSON.stringify(header.tier)}, expected ${tier}`,
    );
  }
  let artifact: ArtifactIdentity | null = null;
  if (header.artifact !== null) {
    const identity = artifactIdentitySchema.safeParse(header.artifact);
    if (!identity.success) {
      fail(
        'identity',
        `GOSA ${tier} header artifact is not a valid artifact identity`,
      );
    }
    artifact = identity.data;
    if (artifact.resolution !== header.resolution) {
      fail(
        'identity',
        `GOSA ${tier} header resolution ${header.resolution} differs from artifact.resolution ${artifact.resolution}`,
      );
    }
  }
  const expected = TIER_COLUMNS[tier];
  const listed = describeColumns(header.columns);
  const normative = describeColumns(expected);
  if (listed !== normative) {
    fail(
      'columns',
      `GOSA ${tier} columns are [${listed}], expected [${normative}]`,
    );
  }
  header.columns.forEach((column, index) => {
    const width = DTYPE_BYTES[expected[index].dtype];
    if (column.length !== header.n_cells * width) {
      fail(
        'column_length',
        `GOSA column ${column.name} is ${column.length} bytes, expected ${header.n_cells} × ${width}`,
      );
    }
  });
  let minimal = 0;
  for (const column of header.columns) {
    if (column.offset !== minimal) {
      fail(
        'offset',
        `GOSA column ${column.name} starts at ${column.offset}, expected ${minimal}`,
      );
    }
    minimal = align8(column.offset + column.length);
  }
  const areaStart = align8(headerEnd);
  const last = header.columns[header.columns.length - 1];
  const end = areaStart + last.offset + last.length;
  if (bytes.byteLength < end) {
    fail(
      'truncated',
      `GOSA container is ${bytes.byteLength} bytes; its columns end at ${end}`,
    );
  }
  if (bytes.byteLength > end) {
    fail(
      'trailing_bytes',
      `GOSA container has ${bytes.byteLength - end} trailing bytes`,
    );
  }
  requireZeros(bytes, headerEnd, areaStart);
  header.columns.forEach((column, index) => {
    if (index > 0) {
      const previous = header.columns[index - 1];
      requireZeros(
        bytes,
        areaStart + previous.offset + previous.length,
        areaStart + column.offset,
      );
    }
  });
  const columns = header.columns.map((column) =>
    bytes.subarray(
      areaStart + column.offset,
      areaStart + column.offset + column.length,
    ),
  );
  return { artifact, columns, header };
}

/** Invert the byte-plane shuffle: encoded[k·n + i] is little-endian byte k of element i. */
export function unshuffle(encoded: Uint8Array, width: number): ArrayBuffer {
  const n = encoded.byteLength / width;
  const raw = new Uint8Array(encoded.byteLength);
  for (let plane = 0; plane < width; plane += 1) {
    const base = plane * n;
    for (let index = 0; index < n; index += 1) {
      raw[index * width + plane] = encoded[base + index];
    }
  }
  return raw.buffer;
}
