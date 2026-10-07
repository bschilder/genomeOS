import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const website = path.resolve(import.meta.dirname, '..');
const dist = path.join(website, 'dist');

function builtPage(route: string): string {
  const filename = path.join(dist, route, 'index.html');
  expect(existsSync(filename), `${filename} was not built`).toBe(true);
  return readFileSync(filename, 'utf8');
}

function viewportOf(html: string): string | undefined {
  return html.match(/<meta name="viewport" content="([^"]*)"/)?.[1];
}

describe('phone viewport contract (mobile sheets design §A.1.1)', () => {
  it.each(['', 'project', 'working-groups', 'contribute'])(
    'keeps /%s at initial scale 1 without viewport-fit',
    (route) => {
      expect(viewportOf(builtPage(route))).toBe(
        'width=device-width, initial-scale=1',
      );
    },
  );

  it('lets only the Atlas page draw under the safe areas', () => {
    expect(viewportOf(builtPage('app'))).toBe(
      'width=device-width, initial-scale=1, viewport-fit=cover',
    );
  });

  it('gives the polygon page the same initial scale', () => {
    expect(viewportOf(builtPage('app/polygon'))).toBe(
      'width=device-width, initial-scale=1',
    );
  });
});

describe('mobile CSS placement (mobile sheets design §A.1.12)', () => {
  it('puts the mobile rules after the dense rules and before the preference blocks', () => {
    const css = readFileSync(
      path.join(website, 'src/styles/atlas.css'),
      'utf8',
    );
    const dense = css.indexOf('/* Dense Atlas UI');
    const mobile = css.indexOf('/* Mobile sheets');
    const end = css.indexOf('/* end of mobile sheet rules */');
    const reducedMotion = css.indexOf(
      '@media (prefers-reduced-motion: reduce)',
    );
    expect(dense).toBeGreaterThan(-1);
    expect(mobile).toBeGreaterThan(dense);
    expect(end).toBeGreaterThan(mobile);
    expect(reducedMotion).toBeGreaterThan(end);
  });
});
