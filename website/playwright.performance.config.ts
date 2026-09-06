import { defineConfig, devices } from '@playwright/test';

delete process.env.NO_COLOR;
process.env.NO_UPDATE_NOTIFIER = '1';

export default defineConfig({
  testDir: './tests',
  testMatch: 'atlas-performance.spec.ts',
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? 'github' : 'list',
  retries: 0,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:4322',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run serve:test',
    url: 'http://127.0.0.1:4322/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
