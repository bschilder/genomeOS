import { execFileSync } from 'node:child_process';

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';

execFileSync(npm, ['run', 'build'], {
  env: {
    ...process.env,
    SITE_URL: 'https://genomeos.github.io',
    BASE_PATH: '/genomeOS',
    OUT_DIR: 'dist-fallback',
    ASTRO_TELEMETRY_DISABLED: '1',
  },
  stdio: 'inherit',
});
