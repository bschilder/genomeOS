/**
 * Test-only GOSA v1 reader and re-packer for decoder negative cases (fast-load design §B.3).
 * Production containers are written only by genomeos/publication/surface_codec.py; this module
 * re-packs golden containers so a test can change exactly one field.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';

import {
  atlasCatalogSchema,
  surfaceArtifactSchema,
  type ArtifactRef,
  type AtlasCatalog,
  type GridEntry,
  type SurfaceArtifact as SurfaceJson,
} from '../../src/atlas/contracts';
import { GosaError, type GosaErrorCode } from '../../src/atlas/gosa/decode';
import { sha256Hex } from '../../src/atlas/gosa/sha256';

export const GOLDEN_DIR = path.resolve(
  import.meta.dirname,
  '../fixtures/atlas/golden',
);

export function fixtureBytes(
  directory: string,
  key: string,
): Uint8Array<ArrayBuffer> {
  return new Uint8Array(readFileSync(path.join(directory, key)));
}

export function goldenBytes(key: string): Uint8Array<ArrayBuffer> {
  return fixtureBytes(GOLDEN_DIR, key);
}

export function goldenCatalogRaw(): unknown {
  return JSON.parse(
    readFileSync(path.join(GOLDEN_DIR, 'catalog.json'), 'utf8'),
  );
}

export function goldenCatalog(): AtlasCatalog {
  return atlasCatalogSchema.parse(goldenCatalogRaw());
}

export function onlyGrid(catalog: AtlasCatalog): {
  entry: GridEntry;
  gridSha256: string;
} {
  const entries = Object.entries(catalog.grids);
  if (entries.length !== 1) {
    throw new Error(`expected exactly one grid, found ${entries.length}`);
  }
  const [gridSha256, entry] = entries[0];
  return { entry, gridSha256 };
}

export function goldenSurfaceJson(ref: ArtifactRef): SurfaceJson {
  return surfaceArtifactSchema.parse(
    JSON.parse(readFileSync(path.join(GOLDEN_DIR, ref.surface_url), 'utf8')),
  );
}

/** A fresh, transferable copy (decoders may receive a buffer they then own). */
export function toBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.slice().buffer;
}

export function redeclare<T extends { bytes: number; sha256: string }>(
  declared: T,
  bytes: Uint8Array,
): T {
  return { ...declared, bytes: bytes.byteLength, sha256: sha256Hex(bytes) };
}

export function refWith(
  ref: ArtifactRef,
  tier: 'detail' | 'render',
  bytes: Uint8Array,
): ArtifactRef {
  return {
    ...ref,
    web: { ...ref.web, [tier]: redeclare(ref.web[tier], bytes) },
  };
}

/** The GosaError code a decode raises, or 'no error'. */
export function gosaCode(run: () => unknown): GosaErrorCode | 'no error' {
  try {
    run();
  } catch (error) {
    if (error instanceof GosaError) return error.code;
    throw error;
  }
  return 'no error';
}

export interface ColumnHeader {
  dtype: string;
  encoding: string;
  length: number;
  name: string;
  offset: number;
}

export type HeaderObject = Record<string, unknown> & {
  columns: ColumnHeader[];
};

export interface SplitContainer {
  header: HeaderObject;
  headerText: string;
  payloads: Uint8Array<ArrayBuffer>[];
}

export function align8(value: number): number {
  return Math.ceil(value / 8) * 8;
}

export function splitContainer(bytes: Uint8Array): SplitContainer {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const headerLength = view.getUint32(8, true);
  const headerText = new TextDecoder().decode(
    bytes.subarray(12, 12 + headerLength),
  );
  const header = JSON.parse(headerText) as HeaderObject;
  const areaStart = align8(12 + headerLength);
  const payloads = header.columns.map((column) =>
    bytes.slice(
      areaStart + column.offset,
      areaStart + column.offset + column.length,
    ),
  );
  return { header, headerText, payloads };
}

/** Python's json.dumps(sort_keys=True, separators=(',', ':')) for ASCII keys. */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) =>
    item && typeof item === 'object' && !Array.isArray(item)
      ? Object.fromEntries(
          Object.entries(item as Record<string, unknown>).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        )
      : item,
  );
}

export function assembleContainer(
  header: HeaderObject,
  payloads: readonly Uint8Array[],
  options: { headerText?: string; offsets?: readonly number[] } = {},
): Uint8Array<ArrayBuffer> {
  let next = 0;
  const columns = header.columns.map((column, index) => {
    const offset = options.offsets?.[index] ?? next;
    const placed = { ...column, length: payloads[index].byteLength, offset };
    next = align8(offset + placed.length);
    return placed;
  });
  const headerBytes = new TextEncoder().encode(
    options.headerText ?? canonicalJson({ ...header, columns }),
  );
  const areaStart = align8(12 + headerBytes.byteLength);
  const last = columns.at(-1);
  const out = new Uint8Array(
    areaStart + (last ? last.offset + last.length : 0),
  );
  out.set([0x47, 0x4f, 0x53, 0x41], 0);
  const view = new DataView(out.buffer);
  view.setUint16(4, 1, true);
  view.setUint16(6, 0, true);
  view.setUint32(8, headerBytes.byteLength, true);
  out.set(headerBytes, 12);
  payloads.forEach((payload, index) =>
    out.set(payload, areaStart + columns[index].offset),
  );
  return out;
}

export function rewriteHeader(
  bytes: Uint8Array,
  change: (header: HeaderObject) => void,
): Uint8Array<ArrayBuffer> {
  const split = splitContainer(bytes);
  change(split.header);
  return assembleContainer(split.header, split.payloads);
}

export function rewriteColumn(
  bytes: Uint8Array,
  name: string,
  change: (payload: Uint8Array<ArrayBuffer>) => Uint8Array<ArrayBuffer>,
): Uint8Array<ArrayBuffer> {
  const split = splitContainer(bytes);
  const index = split.header.columns.findIndex(
    (column) => column.name === name,
  );
  if (index < 0) throw new Error(`no column ${name}`);
  const before = split.payloads[index].byteLength;
  split.payloads[index] = change(split.payloads[index]);
  return assembleContainer(split.header, split.payloads, {
    headerText:
      split.payloads[index].byteLength === before
        ? split.headerText
        : undefined,
  });
}

export function shuffle(
  raw: Uint8Array,
  width: number,
): Uint8Array<ArrayBuffer> {
  const n = raw.byteLength / width;
  const out = new Uint8Array(raw.byteLength);
  for (let plane = 0; plane < width; plane += 1) {
    for (let index = 0; index < n; index += 1) {
      out[plane * n + index] = raw[index * width + plane];
    }
  }
  return out;
}

export function unshuffleBytes(
  encoded: Uint8Array,
  width: number,
): Uint8Array<ArrayBuffer> {
  const n = encoded.byteLength / width;
  const out = new Uint8Array(encoded.byteLength);
  for (let plane = 0; plane < width; plane += 1) {
    for (let index = 0; index < n; index += 1) {
      out[index * width + plane] = encoded[plane * n + index];
    }
  }
  return out;
}

export function editFloats(
  width: 4 | 8,
  edit: (values: number[]) => void,
): (payload: Uint8Array) => Uint8Array<ArrayBuffer> {
  return (payload) => {
    const raw = unshuffleBytes(payload, width);
    const values = Array.from(
      width === 4 ? new Float32Array(raw.buffer) : new Float64Array(raw.buffer),
    );
    edit(values);
    const typed =
      width === 4 ? Float32Array.from(values) : Float64Array.from(values);
    return shuffle(new Uint8Array(typed.buffer), width);
  };
}

/** Delta-then-shuffle u64 cells exactly as fast-load design §B.3 defines `delta_shuffle`. */
export function writeDeltaGrid(
  cells: readonly bigint[],
): Uint8Array<ArrayBuffer> {
  const raw = new Uint8Array(cells.length * 8);
  const view = new DataView(raw.buffer);
  cells.forEach((cell, index) =>
    view.setBigUint64(
      8 * index,
      index === 0 ? cell : BigInt.asUintN(64, cell - cells[index - 1]),
      true,
    ),
  );
  return shuffle(raw, 8);
}

export function laneCells(grid: {
  h3Hi: Uint32Array;
  h3Lo: Uint32Array;
}): bigint[] {
  return Array.from(
    grid.h3Lo,
    (lo, index) => (BigInt(grid.h3Hi[index]) << 32n) | BigInt(lo),
  );
}
