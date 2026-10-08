import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { goldenCatalogRaw } from './support/gosa-builder';

const websiteRoot = path.resolve(import.meta.dirname, '..');
const astro = path.join(
  websiteRoot,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'astro.cmd' : 'astro',
);
const INLINE_CATALOG =
  /<script\b[^>]*\bid="atlas-catalog"[^>]*>([\s\S]*?)<\/script>/;

function build(catalogPath: string, outDir: string): void {
  execFileSync(astro, ['build'], {
    cwd: websiteRoot,
    env: {
      ...process.env,
      ASTRO_TELEMETRY_DISABLED: '1',
      ATLAS_CATALOG_PATH: catalogPath,
      OUT_DIR: outDir,
    },
    stdio: 'pipe',
  });
}

describe('ATLAS_CATALOG_PATH build wiring', () => {
  it('inlines the catalog the build variable names', () => {
    const outDir = mkdtempSync(path.join(tmpdir(), 'genomeos-atlas-catalog-'));
    try {
      build('tests/fixtures/atlas/golden/catalog.json', outDir);
      const html = readFileSync(path.join(outDir, 'app', 'index.html'), 'utf8');
      expect(JSON.parse(html.match(INLINE_CATALOG)![1])).toEqual(
        goldenCatalogRaw(),
      );
    } finally {
      rmSync(outDir, { force: true, recursive: true });
    }
  }, 180_000);

  it('fails the build when the catalog violates the strict schema', () => {
    const outDir = mkdtempSync(path.join(tmpdir(), 'genomeos-atlas-catalog-'));
    const catalog = path.join(outDir, 'broken-catalog.json');
    writeFileSync(catalog, JSON.stringify({ schema_version: 1 }));
    try {
      let output = '';
      try {
        build(catalog, path.join(outDir, 'dist'));
      } catch (error) {
        const failure = error as { stderr?: Buffer; stdout?: Buffer };
        output = `${failure.stdout ?? ''}${failure.stderr ?? ''}`;
      }
      expect(output).toMatch(/fails atlasCatalogSchema/);
    } finally {
      rmSync(outDir, { force: true, recursive: true });
    }
  }, 180_000);
});
