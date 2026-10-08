import { defineConfig, devices } from '@playwright/test';

delete process.env.NO_COLOR;
process.env.NO_UPDATE_NOTIFIER = '1';

/** Opt-in local overrides; CI sets neither and keeps one worker on port 4322. */
function positiveIntegerFromEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return fallback;
  if (!/^[1-9]\d*$/.test(raw))
    throw new Error(`${name} must be a positive integer, got "${raw}"`);
  return Number(raw);
}

const workers = positiveIntegerFromEnv('PLAYWRIGHT_WORKERS', 1);
const port = positiveIntegerFromEnv('PLAYWRIGHT_PORT', 4322);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  testMatch: ['site.spec.ts', 'atlas-mobile.spec.ts'],
  fullyParallel: false,
  workers,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  // A describe tagged with one project's name is filtered out of the other at
  // collection time. A runtime skip would still occupy a slot under --shard.
  projects: [
    {
      name: 'desktop-chromium',
      grepInvert: /@mobile-chromium\b/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chromium',
      grepInvert: /@desktop-chromium\b/,
      use: { ...devices['Pixel 7'] },
    },
  ],
  webServer: {
    command: `npx serve dist -l tcp://127.0.0.1:${port} --no-clipboard`,
    url: `${baseURL}/`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
