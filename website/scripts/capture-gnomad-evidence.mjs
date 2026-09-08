import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { chromium } from 'playwright';

const websiteRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const outputPath = path.resolve(
  websiteRoot,
  '..',
  'docs',
  'figures',
  'gnomad-evidence-navigator.png',
);
const suppliedBaseUrl = process.env.ATLAS_CAPTURE_BASE_URL;
const baseUrl = suppliedBaseUrl ?? 'http://127.0.0.1:4323';
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
  await page.getByRole('button', { name: 'More info' }).click();
  const panel = page.getByRole('complementary', {
    name: 'External variant information',
  });
  await panel.getByRole('button', { name: 'gnomAD' }).click();
  await panel
    .getByRole('button', { name: /Genetic ancestry.*10 groups/ })
    .click();
  await panel
    .getByRole('heading', {
      name: 'Genetic ancestry group frequencies',
    })
    .waitFor();
  await page.screenshot({ path: outputPath });
  process.stdout.write(`Captured 1600×1000: ${outputPath}\n`);
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
