import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { chromium } from '@playwright/test';

const target = process.env.CAPTURE_URL ?? 'http://127.0.0.1:4321/';
const readySelector = process.env.CAPTURE_SELECTOR ?? '#hero-title';
const output = path.resolve(
  process.env.CAPTURE_PATH ??
    path.join(import.meta.dirname, '../../docs/figures/docs-site-homepage.png'),
);
const fullPage = process.env.CAPTURE_FULL_PAGE === '1';

mkdirSync(path.dirname(output), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  reducedMotion: 'reduce',
});

try {
  const response = await page.goto(target, { waitUntil: 'networkidle' });
  if (!response?.ok()) {
    throw new Error(`Preview returned ${response?.status() ?? 'no response'}`);
  }
  await page.locator(readySelector).waitFor();
  await page.evaluate(() => document.fonts.ready);
  if (fullPage) {
    await page.evaluate(async () => {
      const step = Math.max(400, Math.floor(window.innerHeight * 0.8));
      for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise((resolve) => window.setTimeout(resolve, 40));
      }
      window.scrollTo(0, 0);
    });
    await page.locator('img').evaluateAll((images) =>
      Promise.all(
        images.map((image) => {
          if (image.complete) return Promise.resolve();
          return new Promise((resolve) => {
            image.addEventListener('load', resolve, { once: true });
            image.addEventListener('error', resolve, { once: true });
          });
        }),
      ),
    );
  }
  await page.screenshot({ path: output, fullPage });
  console.log(`Captured ${target} at ${output}`);
} finally {
  await browser.close();
}
