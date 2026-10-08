import { defineConfig, devices } from '@playwright/test';

delete process.env.NO_COLOR;
process.env.NO_UPDATE_NOTIFIER = '1';

export default defineConfig({
  testDir: './tests',
  testMatch: ['site.spec.ts', 'atlas-mobile.spec.ts'],
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4322',
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
    command: 'npm run serve:test',
    url: 'http://127.0.0.1:4322/',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
