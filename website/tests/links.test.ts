import { describe, expect, it } from 'vitest';

import { resolveInternalTarget } from '../scripts/check-links.mjs';

describe('resolveInternalTarget', () => {
  it('resolves a root deployment route to its emitted index', () => {
    expect(resolveInternalTarget('/project/', 'index.html', '/')).toBe(
      'project/index.html',
    );
  });

  it('strips the project base from a fallback route', () => {
    expect(
      resolveInternalTarget(
        '/genomeOS/working-groups/',
        'index.html',
        '/genomeOS/',
      ),
    ).toBe('working-groups/index.html');
  });

  it('resolves relative documentation links from the current route', () => {
    expect(
      resolveInternalTarget('./scientific-safeguards/', 'docs/index.html', '/'),
    ).toBe('docs/scientific-safeguards/index.html');
  });

  it('ignores fragments, query strings, and external links', () => {
    expect(
      resolveInternalTarget('#safeguards', 'docs/index.html', '/'),
    ).toBeNull();
    expect(
      resolveInternalTarget(
        'https://github.com/bschilder/genomeOS?q=docs',
        'index.html',
        '/',
      ),
    ).toBeNull();
  });

  it('refuses root-relative links outside a project base', () => {
    expect(() =>
      resolveInternalTarget('/project/', 'index.html', '/genomeOS/'),
    ).toThrow('outside configured base /genomeOS/');
  });
});
