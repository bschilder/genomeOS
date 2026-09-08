import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { chromium } from 'playwright';

import { installAtlasBrowserFixture } from '../tests/atlas-browser-fixture.ts';

const websiteRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const outputPath = path.resolve(
  websiteRoot,
  '..',
  'docs',
  'figures',
  'cesium-globe-explorer.png',
);
const suppliedBaseUrl = process.env.ATLAS_CAPTURE_BASE_URL;
const baseUrl = suppliedBaseUrl ?? 'http://127.0.0.1:4323';

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

let server;
if (!suppliedBaseUrl) {
  server = spawn(
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
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    deviceScaleFactor: 1,
    viewport: { height: 1440, width: 2560 },
  });
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error));
  page.on('console', (entry) => {
    if (entry.type() === 'error') consoleErrors.push(entry.text());
  });
  await installAtlasBrowserFixture(page, {
    focus: { lat: 8, lon: 0 },
    surfaceScope: 'regional',
  });
  const query = new URLSearchParams({
    elevation: process.env.ATLAS_CAPTURE_ELEVATION ?? 'true',
    entity: process.env.ATLAS_CAPTURE_ENTITY ?? 'hbs-rs334',
    exaggeration: '2',
    heading: '0',
    height: '1400000',
    lat: '8',
    layers:
      process.env.ATLAS_CAPTURE_LAYERS ??
      'surface,observations,support,context',
    lon: '0',
    metric: process.env.ATLAS_CAPTURE_METRIC ?? 'post_mean',
    pitch: '-90',
    version: process.env.ATLAS_CAPTURE_VERSION ?? 'v3/map-2026-08',
    view: process.env.ATLAS_CAPTURE_VIEW ?? 'globe',
  });
  await page.goto(`${baseUrl}/app/?${query}`);
  try {
    await page
      .locator('[data-atlas-ready="true"]')
      .waitFor({ timeout: 60_000 });
  } catch (error) {
    const panel = page.locator('.cesium-widget-errorPanel');
    if (await panel.isVisible()) {
      process.stderr.write(`${await panel.innerText()}\n`);
    }
    for (const message of consoleErrors) process.stderr.write(`${message}\n`);
    throw error;
  }
  await page.waitForTimeout(1_000);
  if (pageErrors.length > 0) throw pageErrors[0];
  await page.screenshot({ path: outputPath });
  const dimensions = await page.evaluate(() => ({
    height: window.innerHeight,
    width: window.innerWidth,
  }));
  process.stdout.write(
    `Captured ${dimensions.width}×${dimensions.height}: ${outputPath}\n`,
  );
} finally {
  await browser?.close();
  if (server && server.exitCode === null) {
    server.kill('SIGTERM');
    await Promise.race([
      once(server, 'exit'),
      new Promise((resolve) => setTimeout(resolve, 2_000)),
    ]);
  }
}
