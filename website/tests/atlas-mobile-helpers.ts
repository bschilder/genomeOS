/** Shared Playwright helpers for the Atlas phone layout (mobile sheets design 2026-10-07 §A.3). */

import { expect, test, type Page, type TestInfo } from '@playwright/test';

export const PHONE_PROFILES = [
  { name: 'Pixel 7', use: {} },
  {
    name: '360x780',
    use: {
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true,
      viewport: { height: 780, width: 360 },
    },
  },
  {
    name: '390x844',
    use: {
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true,
      viewport: { height: 844, width: 390 },
    },
  },
] as const;

export function skipUnlessProject(
  testInfo: TestInfo,
  project: 'desktop-chromium' | 'mobile-chromium',
): void {
  test.skip(
    testInfo.project.name !== project,
    `runs only in the ${project} project`,
  );
}

export async function waitForAtlasReady(page: Page): Promise<void> {
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });
}
