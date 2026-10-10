import { execFileSync } from 'node:child_process';
import path from 'node:path';

export function setup(): void {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  execFileSync(npm, ['run', 'build'], {
    cwd: path.resolve(import.meta.dirname, '../..'),
    env: {
      ...process.env,
      ASTRO_TELEMETRY_DISABLED: '1',
      // vitest sets NODE_ENV=test; the bundle checks must see what Pages ships (fast-load §B.8).
      NODE_ENV: 'production',
      // Unit and content tests read this dist/; never inline the e2e catalog here, and keep the
      // production 15 s stall window (a shell export of the e2e override would fail the build).
      ATLAS_CATALOG_PATH: 'public/data/atlas/catalog.json',
      PUBLIC_ATLAS_REQUEST_STALL_MS: '',
      // #422: unit tests read a build without analytics (tests/analytics-build.test.ts), whatever
      // the shell exports.
      PUBLIC_GA_MEASUREMENT_ID: '',
    },
    stdio: 'inherit',
  });
}
