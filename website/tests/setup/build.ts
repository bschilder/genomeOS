import { execFileSync } from 'node:child_process';
import path from 'node:path';

export function setup(): void {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  execFileSync(npm, ['run', 'build'], {
    cwd: path.resolve(import.meta.dirname, '../..'),
    env: { ...process.env, ASTRO_TELEMETRY_DISABLED: '1' },
    stdio: 'inherit',
  });
}
