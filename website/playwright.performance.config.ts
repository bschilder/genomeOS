import { defineConfig, devices } from '@playwright/test';

import { playwrightPort } from './tests/setup/playwright-env';

delete process.env.NO_COLOR;
process.env.NO_UPDATE_NOTIFIER = '1';

const port = playwrightPort();
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  testMatch: 'atlas-performance.spec.ts',
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? 'github' : 'list',
  retries: 0,
  workers: 1,
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
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
