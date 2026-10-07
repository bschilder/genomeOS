import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import {
  decodeDetail,
  decodeGrid,
  decodeRender,
  GOSA_ERROR_CODES,
  type GosaErrorCode,
  type GosaTier,
} from '../src/atlas/gosa/decode';
import {
  fixtureBytes,
  GOLDEN_DIR,
  goldenBytes,
  goldenCatalog,
  gosaCode,
  onlyGrid,
  toBuffer,
} from './support/gosa-builder';

/** Byte copy of tests/fixtures/atlas-web/mutations (tests/test_atlas_web_fixtures.py asserts it). */
const CORPUS = path.join(GOLDEN_DIR, 'mutations');

/**
 * The eleven mutation classes spec §B.3 names, each with the corpus file that carries it and the
 * code both decoders must give. Several classes share a code (five are `h3_cell`, two
 * `grid_order`), so coverage is checked per file, not per code. Mirrors `SPEC_MUTATIONS` in
 * tests/test_atlas_web_fixtures.py.
 */
const SPEC_MUTATIONS: readonly (readonly [
  specClass: string,
  file: string,
  code: GosaErrorCode,
])[] = [
  ['reserved = 1', 'grid-reserved-1.gosa', 'reserved'],
  ['pad byte 0x01', 'render-pad-byte.gosa', 'padding'],
  ['one trailing byte', 'grid-trailing-byte.gosa', 'trailing_bytes'],
  ['offset + 8', 'render-offset-plus-8.gosa', 'offset'],
  ['MSB-first planes', 'grid-msb-first-planes.gosa', 'grid_order'],
  ['a zero delta', 'grid-zero-delta.gosa', 'grid_order'],
  ['a set reserved H3 bit', 'grid-reserved-h3-bit.gosa', 'h3_cell'],
  ['mode ≠ 1', 'grid-mode-2.gosa', 'h3_cell'],
  ['a digit 7 inside the resolution', 'grid-digit-7.gosa', 'h3_cell'],
  ['base cell > 121', 'grid-base-cell-122.gosa', 'h3_cell'],
  ['wrong resolution', 'grid-wrong-resolution.gosa', 'h3_cell'],
];

interface MutationCase {
  artifact: string | null;
  base: string;
  bytes: number;
  code: GosaErrorCode;
  file: string;
  grid_sha256: string;
  sha256: string;
  tier: GosaTier;
}

const manifest = JSON.parse(
  readFileSync(path.join(CORPUS, 'manifest.json'), 'utf8'),
) as { codes: string[]; mutations: MutationCase[] };
const files = readdirSync(CORPUS)
  .filter((name) => name.endsWith('.gosa'))
  .sort();

const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const grid = decodeGrid(toBuffer(goldenBytes(entry.url)), {
  entry,
  gridSha256,
});

/** Decode a mutated file with its own digest and size declared, so structure is what is tested. */
function decodeCase(testCase: MutationCase): unknown {
  const bytes = fixtureBytes(CORPUS, testCase.file);
  const declared = { bytes: testCase.bytes, sha256: testCase.sha256 };
  const { tier } = testCase;
  if (tier === 'grid') {
    return decodeGrid(toBuffer(bytes), {
      entry: { ...entry, ...declared },
      gridSha256: testCase.grid_sha256,
    });
  }
  const ref = catalog.artifacts.find(({ id }) => id === testCase.artifact);
  if (!ref)
    throw new Error(`corpus names unknown artifact ${testCase.artifact}`);
  const redeclared: ArtifactRef =
    tier === 'render'
      ? {
          ...ref,
          web: { ...ref.web, render: { ...ref.web.render, ...declared } },
        }
      : {
          ...ref,
          web: { ...ref.web, detail: { ...ref.web.detail, ...declared } },
        };
  if (tier === 'render') {
    return decodeRender(toBuffer(bytes), { grid, ref: redeclared });
  }
  const render = decodeRender(toBuffer(goldenBytes(ref.web.render.url)), {
    grid,
    ref,
  });
  return decodeDetail(toBuffer(bytes), { grid, ref: redeclared, render });
}

describe('shared GOSA mutation corpus (fast-load design §B.3)', () => {
  it('shares the Python error vocabulary in check order', () => {
    expect([...GOSA_ERROR_CODES]).toEqual(manifest.codes);
  });

  it('lists every corpus file exactly once', () => {
    expect(manifest.mutations.map(({ file }) => file).sort()).toEqual(files);
  });

  it('names each of the eleven spec classes once, each in its own corpus file', () => {
    expect(new Set(SPEC_MUTATIONS.map(([specClass]) => specClass)).size).toBe(
      11,
    );
    expect(new Set(SPEC_MUTATIONS.map(([, file]) => file)).size).toBe(11);
  });

  it.each(SPEC_MUTATIONS)(
    'holds the spec class "%s" as %s, refused with %s',
    (_specClass, file, code) => {
      const listed = manifest.mutations.filter(
        (testCase) => testCase.file === file,
      );
      expect(listed.map((testCase) => testCase.code)).toEqual([code]);
      expect(
        listed.map((testCase) => gosaCode(() => decodeCase(testCase))),
      ).toEqual([code]);
    },
  );

  it.each(
    manifest.mutations.map((testCase) => [testCase.file, testCase] as const),
  )('rejects %s with the Python decoder’s error code', (_file, testCase) => {
    expect(gosaCode(() => decodeCase(testCase))).toBe(testCase.code);
  });
});
