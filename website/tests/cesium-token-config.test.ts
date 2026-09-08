import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const websiteRoot = path.resolve(import.meta.dirname, '..');
const repositoryRoot = path.resolve(websiteRoot, '..');

describe('Cesium ion browser-token wiring', () => {
  it('hydrates a token loaded from the repository environment boundary', () => {
    const mode = `cesium-regression-${process.pid}`;
    const environmentPath = path.join(repositoryRoot, `.env.${mode}`);
    const outDir = mkdtempSync(path.join(tmpdir(), 'genomeos-cesium-env-'));
    const childEnvironment = { ...process.env };
    delete childEnvironment.CESIUM_TOKEN;
    Object.assign(childEnvironment, {
      ASTRO_TELEMETRY_DISABLED: '1',
      OUT_DIR: outDir,
    });

    writeFileSync(
      environmentPath,
      'CESIUM_TOKEN=cesium-regression-sentinel\n',
      'utf8',
    );
    try {
      execFileSync(
        path.join(
          websiteRoot,
          'node_modules',
          '.bin',
          process.platform === 'win32' ? 'astro.cmd' : 'astro',
        ),
        ['build', '--mode', mode],
        {
          cwd: websiteRoot,
          env: childEnvironment,
          stdio: 'pipe',
        },
      );
      const appHtml = readFileSync(
        path.join(outDir, 'app', 'index.html'),
        'utf8',
      );

      expect(appHtml).toContain('cesium-regression-sentinel');
    } finally {
      rmSync(environmentPath, { force: true });
      rmSync(outDir, { force: true, recursive: true });
    }
  }, 30_000);
});
