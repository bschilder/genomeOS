/** E2E build wiring for the Atlas browser fixture (fast-load design §B.8). */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const websiteRoot = path.resolve(import.meta.dirname, '..');
const E2E_CATALOG = 'tests/fixtures/atlas/e2e/catalog.json';

function scripts(): Record<string, string> {
  return (
    JSON.parse(
      readFileSync(path.join(websiteRoot, 'package.json'), 'utf8'),
    ) as {
      scripts: Record<string, string>;
    }
  ).scripts;
}

describe('Atlas e2e build wiring', () => {
  it('builds browser tests and fixture captures from the committed e2e catalog', () => {
    const npm = scripts();
    // The stall window is stretched only here (fast-load design §B.2 keeps 15 s in production):
    // Task 76 (B5.7) holds the detail tier until it releases it.
    expect(npm['build:e2e']).toBe(
      `ATLAS_CATALOG_PATH=${E2E_CATALOG} PUBLIC_ATLAS_REQUEST_STALL_MS=120000 npm run build`,
    );
    for (const [name, script] of Object.entries(npm))
      if (name !== 'build:e2e')
        expect(script, name).not.toContain('PUBLIC_ATLAS_REQUEST_STALL_MS');
    expect(npm['test:e2e']).toBe('npm run build:e2e && playwright test');
    expect(npm['capture:atlas']).toBe(
      'npm run build:e2e && node scripts/capture-atlas.mjs',
    );
    expect(npm['capture:studs']).toBe(
      'npm run build:e2e && node scripts/capture-observation-studs.mjs',
    );
    expect(npm['capture:atlas-mobile']).toBe(
      'npm run build:e2e && ATLAS_CAPTURE_PROFILE=mobile node scripts/capture-atlas.mjs',
    );
    const catalog = JSON.parse(
      readFileSync(path.join(websiteRoot, E2E_CATALOG), 'utf8'),
    ) as { artifacts: unknown[]; grids: Record<string, unknown> };
    expect(catalog.artifacts).toHaveLength(30);
    expect(Object.keys(catalog.grids)).toHaveLength(1);
  });

  it('pins the unit-test build to the production catalog', () => {
    const setup = readFileSync(
      path.join(websiteRoot, 'tests/setup/build.ts'),
      'utf8',
    );
    expect(setup).toContain(
      "ATLAS_CATALOG_PATH: 'public/data/atlas/catalog.json'",
    );
    expect(setup).toContain("PUBLIC_ATLAS_REQUEST_STALL_MS: ''");
  });

  it('collects only *.test.ts files so Playwright specs never run under vitest', () => {
    const config = readFileSync(
      path.join(websiteRoot, 'vitest.config.ts'),
      'utf8',
    );
    expect(config).toContain("include: ['tests/**/*.test.ts']");
    expect(config).not.toContain('exclude');
  });
});
