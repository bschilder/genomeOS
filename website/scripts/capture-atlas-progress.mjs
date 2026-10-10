import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { chromium } from 'playwright';

import { delayArtifactTier } from '../tests/atlas-browser-fixture.ts';

const websiteRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const outputPath = path.resolve(
  websiteRoot,
  '..',
  'docs',
  'figures',
  'atlas-loading-progress.png',
);
const baseUrl = 'http://127.0.0.1:4323';
const neutralTile = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAFAgIAvPp7WQAAAABJRU5ErkJggg==',
  'base64',
);

async function waitForServer(url) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

/** Fail unless the delayed tier's request reached its hold; it may start after the status. */
async function waitForHeldRequest(delay, label) {
  const deadline = Date.now() + 5_000;
  while (delay.hits() === 0) {
    if (Date.now() >= deadline)
      throw new Error(
        `The ${label} request never reached delayArtifactTier's hold, so the capture would not show its loading state.`,
      );
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

const server = spawn(
  process.execPath,
  [
    path.join(websiteRoot, 'node_modules', 'serve', 'build', 'main.js'),
    'dist',
    '-l',
    'tcp://127.0.0.1:4323',
    '--no-clipboard',
  ],
  { cwd: websiteRoot, stdio: 'ignore' },
);
await waitForServer(`${baseUrl}/app/`);

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    deviceScaleFactor: 1,
    viewport: { height: 1000, width: 1600 },
  });
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.fulfill({
      body: neutralTile,
      contentType: 'image/png',
      status: 200,
    }),
  );
  await page.goto(`${baseUrl}/app/`);
  await page.locator('[data-atlas-ready="true"]').waitFor({
    timeout: 60_000,
  });
  const renderDelay = await delayArtifactTier(
    page,
    'g6pd-deficiency',
    'render',
    5_000,
    { appUrl: `${baseUrl}/app/` },
  );
  await page
    .getByRole('button', { name: /Select dataset\. Current dataset:/ })
    .click();
  await page.locator('[role="option"][data-map-id="g6pd-deficiency"]').click();
  const status = page.locator('[data-atlas-status-slot]');
  await status.getByText(/Loading G6PD deficiency/).waitFor();
  // The status alone does not prove the hold matched: with a stale tier key the render tier
  // slips through, and the figure freezes whichever phase happens to be on screen.
  await waitForHeldRequest(renderDelay, 'G6PD render tier');
  await page.waitForTimeout(300);
  await page.screenshot({ path: outputPath });
  process.stdout.write(`Captured 1600×1000: ${outputPath}\n`);
} finally {
  await browser?.close();
  if (server.exitCode === null) {
    server.kill('SIGTERM');
    await Promise.race([
      once(server, 'exit'),
      new Promise((resolve) => setTimeout(resolve, 2_000)),
    ]);
  }
}
