import { defineConfig, devices } from '@playwright/test';

import {
  playwrightPort,
  playwrightWorkers,
} from './tests/setup/playwright-env';

delete process.env.NO_COLOR;
process.env.NO_UPDATE_NOTIFIER = '1';

const port = playwrightPort();
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  testMatch: ['site.spec.ts', 'atlas-mobile.spec.ts'],
  fullyParallel: false,
  workers: playwrightWorkers(),
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
    // package.json `serve:test` is the one definition of the test server; it reads the port.
    command: 'npm run serve:test',
    env: { PLAYWRIGHT_PORT: String(port) },
    url: `${baseURL}/`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
