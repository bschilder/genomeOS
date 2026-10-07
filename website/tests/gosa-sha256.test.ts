import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { sha256Hex } from '../src/atlas/gosa/sha256';

describe('sha256Hex', () => {
  it('matches the FIPS 180-2 test vectors', () => {
    expect(sha256Hex(new Uint8Array())).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
    expect(sha256Hex(new TextEncoder().encode('abc'))).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  it('agrees with node:crypto on a megabyte of deterministic bytes', () => {
    const bytes = Uint8Array.from(
      { length: 1 << 20 },
      (_, index) => (index * 2654435761) >>> 24,
    );
    expect(sha256Hex(bytes)).toBe(
      createHash('sha256').update(bytes).digest('hex'),
    );
  });

  it('hashes only the bytes a view covers', () => {
    const backing = new TextEncoder().encode('xxabcxx');
    expect(sha256Hex(backing.subarray(2, 5))).toBe(
      sha256Hex(new TextEncoder().encode('abc')),
    );
  });

  it('is pinned to an exact @noble/hashes release', () => {
    const manifest = JSON.parse(
      readFileSync(
        path.resolve(import.meta.dirname, '../package.json'),
        'utf8',
      ),
    ) as { dependencies: Record<string, string> };
    expect(manifest.dependencies['@noble/hashes']).toBe('2.4.0');
  });
});
