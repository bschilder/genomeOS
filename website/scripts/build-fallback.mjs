import { execFileSync } from 'node:child_process';

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';

execFileSync(npm, ['run', 'build'], {
  env: {
    ...process.env,
    SITE_URL: 'https://genomeos.github.io',
    BASE_PATH: '/genomeOS',
    OUT_DIR: 'dist-fallback',
    ASTRO_TELEMETRY_DISABLED: '1',
    // #422: the /genomeOS/ fallback never reports to Google Analytics.
    PUBLIC_GA_MEASUREMENT_ID: '',
  },
  stdio: 'inherit',
});
