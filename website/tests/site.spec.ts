import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const topLevelRoutes = [
  '/',
  '/project/',
  '/working-groups/',
  '/contribute/',
  '/app/',
  '/docs/',
];

for (const route of topLevelRoutes) {
  test(`${route} has one primary heading and no serious axe violations`, async ({
    page,
  }) => {
    await page.goto(route);
    await expect(page.locator('h1')).toHaveCount(1);

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    const blocking = results.violations.filter(({ impact }) =>
      ['serious', 'critical'].includes(impact ?? ''),
    );
    expect(blocking).toEqual([]);
  });
}

test('primary navigation reaches working groups and exposes GitHub access', async ({
  page,
  isMobile,
}) => {
  await page.goto('/');
  await expect(
    page.getByRole('link', { name: 'View genomeOS on GitHub' }).first(),
  ).toHaveAttribute('href', 'https://github.com/bschilder/genomeOS');

  if (isMobile) {
    await page.getByText('Menu', { exact: true }).click();
    await page
      .getByRole('navigation', { name: 'Mobile navigation' })
      .getByRole('link', { name: 'Working groups' })
      .click();
  } else {
    await page
      .getByRole('navigation', { name: 'Primary navigation' })
      .getByRole('link', { name: 'Working groups' })
      .click();
  }

  await expect(page).toHaveURL(/\/working-groups\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Choose the part of the problem',
  );
});

test('project page labels all three capability states', async ({ page }) => {
  await page.goto('/project/');
  await expect(
    page.getByRole('heading', { name: 'Available now' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'In active development' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Future exploration' }),
  ).toBeVisible();
});

test('working-group page links each group to issue work', async ({ page }) => {
  await page.goto('/working-groups/');
  await expect(
    page.getByRole('link', { name: 'Browse matching issues' }),
  ).toHaveCount(3);
  await expect(page.getByText('Group forming')).toHaveCount(3);
});

test('mobile navigation is a keyboard-operable disclosure', async ({
  page,
  isMobile,
}) => {
  test.skip(
    !isMobile,
    'mobile navigation is only rendered as the active control on narrow screens',
  );
  await page.goto('/');
  const menu = page.getByText('Menu', { exact: true });
  await menu.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('navigation', { name: 'Mobile navigation' }),
  ).toBeVisible();
  await expect(
    page
      .getByRole('navigation', { name: 'Mobile navigation' })
      .getByRole('link', { name: 'Technical docs' }),
  ).toBeVisible();
});

test('404 page offers three recovery routes', async ({ page }) => {
  await page.goto('/404.html');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'That route is outside the atlas.',
  );
  const recovery = page.locator('main');
  await expect(recovery.getByRole('link', { name: /Home/ })).toBeVisible();
  await expect(
    recovery.getByRole('link', { name: /Contribute/ }),
  ).toBeVisible();
  await expect(
    recovery.getByRole('link', { name: /Technical docs/ }),
  ).toBeVisible();
});

for (const route of topLevelRoutes) {
  test(`${route} does not create horizontal page scrolling`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    await page.goto(route);

    const hasHorizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
}

test('reduced-motion preferences disable decorative hero movement', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');

  const animationName = await page
    .locator('.hero__image')
    .evaluate((element) => getComputedStyle(element).animationName);
  expect(animationName).toBe('none');
});

test('public typography keeps body and supporting text comfortably large', async ({
  page,
}) => {
  await page.goto('/');

  const typeSizes = await page.evaluate(() => {
    const selectors = [
      'body',
      '.desktop-nav a',
      '.section-kicker',
      '.site-footer p',
      '.mission-copy p',
    ];
    return Object.fromEntries(
      selectors.map((selector) => [
        selector,
        Number.parseFloat(
          getComputedStyle(document.querySelector(selector)!).fontSize,
        ),
      ]),
    );
  });

  expect(typeSizes.body).toBeGreaterThanOrEqual(19);
  for (const [selector, size] of Object.entries(typeSizes)) {
    if (selector !== 'body') expect(size).toBeGreaterThanOrEqual(16);
  }
});

test('metric digits use a common height and baseline', async ({ page }) => {
  await page.goto('/');

  const numericStyle = await page
    .locator('.metric data')
    .first()
    .evaluate((element) => ({
      family: getComputedStyle(element).fontFamily,
      variant: getComputedStyle(element).fontVariantNumeric,
    }));
  expect(numericStyle.family).toContain('Figtree');
  expect(numericStyle.variant).toContain('lining-nums');
  expect(numericStyle.variant).toContain('tabular-nums');
});

test('multi-scale illustrations load with accessible descriptions', async ({
  page,
}) => {
  await page.goto('/project/');
  const images = page.locator('.vision-card img');
  await expect(images).toHaveCount(3);
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded();
    await expect(image).toHaveJSProperty('complete', true);
    expect(await image.getAttribute('alt')).not.toBe('');
    expect(
      await image.evaluate((element: HTMLImageElement) => element.naturalWidth),
    ).toBe(1536);
  }
});

test('introduction pages avoid unexplained internal milestone codes', async ({
  page,
}) => {
  for (const route of ['/', '/project/', '/app/']) {
    await page.goto(route);
    const text = await page.locator('main').innerText();
    expect(text).not.toMatch(/\bP[0-9]+\b/);
  }
});

test('application cards reveal on scroll and respond to hover', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'hover movement is a pointer interaction');
  await page.goto('/');

  const card = page.locator('.application-card').first();
  await card.scrollIntoViewIfNeeded();
  await expect(card).toHaveClass(/is-visible/);
  const restingTransform = await card.evaluate(
    (element) => getComputedStyle(element).transform,
  );
  await card.hover();
  await page.waitForTimeout(250);
  const hoverTransform = await card.evaluate(
    (element) => getComputedStyle(element).transform,
  );
  expect(hoverTransform).not.toBe(restingTransform);
});
