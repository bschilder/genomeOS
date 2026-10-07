import { cellToChildren, splitLongToH3Index } from 'h3-js';
import { describe, expect, it } from 'vitest';

import type { GridEntry } from '../src/atlas/contracts';
import { decodeGrid } from '../src/atlas/gosa/decode';
import {
  assembleContainer,
  goldenBytes,
  goldenCatalog,
  goldenSurfaceJson,
  gosaCode,
  laneCells,
  onlyGrid,
  redeclare,
  rewriteColumn,
  rewriteHeader,
  splitContainer,
  toBuffer,
  writeDeltaGrid,
} from './support/gosa-builder';

const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const golden = goldenBytes(entry.url);
const goldenGrid = decodeGrid(toBuffer(golden), { entry, gridSha256 });
const goldenCells = laneCells(goldenGrid);

function decodeMutated(
  bytes: Uint8Array,
  overrides: Partial<GridEntry> = {},
  key = gridSha256,
) {
  return decodeGrid(toBuffer(bytes), {
    entry: { ...redeclare(entry, bytes), ...overrides },
    gridSha256: key,
  });
}

function withCells(cells: readonly bigint[]): Uint8Array<ArrayBuffer> {
  return rewriteColumn(golden, 'h3', () => writeDeltaGrid(cells));
}

function hex(cell: bigint): string {
  return cell.toString(16);
}

describe('decodeGrid on the golden grid', () => {
  it('reconstructs every cell of every artifact in grid order', () => {
    expect(goldenGrid.n).toBe(entry.n_cells);
    expect(goldenGrid.resolution).toBe(entry.resolution);
    expect(goldenGrid.gridSha256).toBe(gridSha256);
    const cells = Array.from({ length: goldenGrid.n }, (_, row) =>
      splitLongToH3Index(goldenGrid.h3Lo[row], goldenGrid.h3Hi[row]),
    );
    for (const ref of catalog.artifacts) {
      expect(cells).toEqual(
        goldenSurfaceJson(ref).cells.map(({ h3_index }) => h3_index),
      );
    }
  });

  it('returns lanes that own their buffers so they can be transferred', () => {
    expect(goldenGrid.h3Lo.byteOffset).toBe(0);
    expect(goldenGrid.h3Lo.buffer.byteLength).toBe(goldenGrid.n * 4);
    expect(goldenGrid.h3Hi.buffer).not.toBe(goldenGrid.h3Lo.buffer);
  });

  it('reports verify and decode phases to the timing hook', () => {
    const phases: string[] = [];
    decodeGrid(toBuffer(golden), { entry, gridSha256 }, (phase, start, end) => {
      expect(end).toBeGreaterThanOrEqual(start);
      phases.push(phase);
    });
    expect(phases).toEqual(['verify', 'decode']);
  });

  it('re-packs byte-for-byte through the test builder', () => {
    const split = splitContainer(golden);
    expect(assembleContainer(split.header, split.payloads)).toEqual(golden);
  });
});

describe('decodeGrid hard errors', () => {
  it('refuses bytes that differ from the catalog digest or size', () => {
    const flipped = golden.slice();
    flipped[flipped.length - 1] ^= 0xff;
    expect(
      gosaCode(() => decodeGrid(toBuffer(flipped), { entry, gridSha256 })),
    ).toBe('container_sha256');
    expect(
      gosaCode(() =>
        decodeGrid(toBuffer(golden), {
          entry: { ...entry, bytes: entry.bytes + 1 },
          gridSha256,
        }),
      ),
    ).toBe('container_sha256');
  });

  it('raises truncated for a container shorter than its preamble', () => {
    expect(gosaCode(() => decodeMutated(golden.slice(0, 8)))).toBe('truncated');
  });

  it.each([
    // A block body with an explicit `void` return: a `void (assignment)` arrow inside an
    // `as const` table is TS7024 (implicit any return type).
    [
      'magic',
      (bytes: Uint8Array): void => {
        bytes[0] = 0x58;
      },
    ],
    [
      'format_version',
      (bytes: Uint8Array) => new DataView(bytes.buffer).setUint16(4, 2, true),
    ],
    [
      'reserved',
      (bytes: Uint8Array) => new DataView(bytes.buffer).setUint16(6, 1, true),
    ],
  ] as const)('raises %s for a damaged preamble', (code, damage) => {
    const bytes = golden.slice();
    damage(bytes);
    expect(gosaCode(() => decodeMutated(bytes))).toBe(code);
  });

  it('raises trailing_bytes for one extra byte', () => {
    const bytes = new Uint8Array(golden.byteLength + 1);
    bytes.set(golden);
    expect(gosaCode(() => decodeMutated(bytes))).toBe('trailing_bytes');
  });

  it('raises padding for a non-zero pad byte after the header', () => {
    const split = splitContainer(golden);
    const textBytes = new TextEncoder().encode(split.headerText).byteLength;
    const space = (12 + textBytes) % 8 === 0 ? ' ' : '';
    const padded = assembleContainer(split.header, split.payloads, {
      headerText: split.headerText + space,
    });
    padded[12 + textBytes + space.length] = 0x01;
    expect(gosaCode(() => decodeMutated(padded))).toBe('padding');
  });

  it('raises offset for a non-minimal column offset', () => {
    const split = splitContainer(golden);
    const shifted = assembleContainer(split.header, split.payloads, {
      offsets: [8],
    });
    expect(gosaCode(() => decodeMutated(shifted))).toBe('offset');
  });

  it('raises header_encoding for invalid UTF-8 and header_schema for a loose header', () => {
    const bytes = golden.slice();
    const { headerText } = splitContainer(golden);
    // Byte offset of the `g` in the tier value `"grid"`, counted in UTF-8 bytes after the preamble.
    const at =
      12 +
      new TextEncoder().encode(
        headerText.slice(0, headerText.indexOf('"grid"')),
      ).byteLength;
    bytes[at + 1] = 0xff;
    expect(gosaCode(() => decodeMutated(bytes))).toBe('header_encoding');
    expect(
      gosaCode(() =>
        decodeMutated(rewriteHeader(golden, (header) => (header.extra = 1))),
      ),
    ).toBe('header_schema');
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(golden, (header) => (header.n_cells = true)),
        ),
      ),
    ).toBe('header_schema');
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(golden, (header) => (header.artifact = {})),
        ),
      ),
    ).toBe('header_schema');
  });

  it('raises tier, columns and column_length for a wrong declared layout', () => {
    // A schema-valid render header (identity and source present) requested as a grid.
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(golden, (header) => {
            header.tier = 'render';
            header.artifact = { id: 'not-checked-before-the-tier' };
            header.source_surface_sha256 = 'a'.repeat(64);
          }),
        ),
      ),
    ).toBe('tier');
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(
            golden,
            (header) => (header.columns[0].encoding = 'shuffle'),
          ),
        ),
      ),
    ).toBe('columns');
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(golden, (header) => (header.columns[0].name = 'cell')),
        ),
      ),
    ).toBe('columns');
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(golden, (header) => {
            header.n_cells = Number(header.n_cells) + 1;
          }),
        ),
      ),
    ).toBe('column_length');
  });

  it('binds n_cells and resolution to the catalog grid entry', () => {
    expect(
      gosaCode(() => decodeMutated(golden, { n_cells: entry.n_cells + 1 })),
    ).toBe('n_cells');
    expect(
      gosaCode(() =>
        decodeMutated(golden, { resolution: entry.resolution + 1 }),
      ),
    ).toBe('header_schema');
  });

  it('raises grid_order for a zero delta and for a decreasing pair', () => {
    const repeated = [...goldenCells];
    repeated[1] = repeated[0];
    expect(gosaCode(() => decodeMutated(withCells(repeated)))).toBe(
      'grid_order',
    );
    const swapped = [...goldenCells];
    [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
    expect(gosaCode(() => decodeMutated(withCells(swapped)))).toBe(
      'grid_order',
    );
  });

  it('raises h3_cell for an invalid cell and for a cell at another resolution', () => {
    const invalid = [...goldenCells];
    invalid[invalid.length - 1] += 1n;
    expect(gosaCode(() => decodeMutated(withCells(invalid)))).toBe('h3_cell');
    const finer = [...goldenCells];
    finer[finer.length - 1] = BigInt(
      `0x${cellToChildren(hex(finer[finer.length - 1]), entry.resolution + 1)[0]}`,
    );
    expect(gosaCode(() => decodeMutated(withCells(finer)))).toBe('h3_cell');
  });

  it('raises grid_sha256 when the header or catalog key disagrees with the cells', () => {
    expect(
      gosaCode(() =>
        decodeMutated(
          rewriteHeader(
            golden,
            (header) => (header.grid_sha256 = '0'.repeat(64)),
          ),
        ),
      ),
    ).toBe('grid_sha256');
    expect(gosaCode(() => decodeMutated(golden, {}, 'f'.repeat(64)))).toBe(
      'grid_sha256',
    );
  });
});
