import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const css = readFileSync(
  path.resolve(import.meta.dirname, '../src/styles/global.css'),
  'utf8',
);

/** The declarations of the first top-level rule for `selector`, comments removed. */
function declarations(selector: string): string[] {
  const start = css.indexOf(`\n${selector} {`);
  expect(start, `${selector} rule`).toBeGreaterThan(-1);
  return css
    .slice(css.indexOf('{', start) + 1, css.indexOf('}', start))
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split(';')
    .map((declaration) => declaration.trim().replace(/\s+/g, ' '))
    .filter(Boolean);
}

describe('the header Menu panel', () => {
  it('caps its height in vh first, for browsers without dynamic viewport units', () => {
    expect(
      declarations('.mobile-nav nav').filter((declaration) =>
        declaration.startsWith('max-height:'),
      ),
    ).toEqual([
      'max-height: max(6rem, 100vh - var(--site-header-height) - 1rem)',
      'max-height: max(6rem, 100dvh - var(--site-header-height) - 1rem)',
    ]);
  });
});
