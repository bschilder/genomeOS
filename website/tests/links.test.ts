import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { resolveInternalTarget } from '../scripts/check-links.mjs';

const dist = path.resolve(import.meta.dirname, '../dist');

function htmlFiles(directory: string): string[] {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory()
      ? htmlFiles(target)
      : entry.name.endsWith('.html')
        ? [target]
        : [];
  });
}

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

describe('external GitHub links', () => {
  it('opens every github.com link in a separate, protected tab', () => {
    const anchors = htmlFiles(dist).flatMap((filename) => {
      const html = readFileSync(filename, 'utf8');
      return html.match(/<a\b[^>]*href="https:\/\/github\.com[^>]*>/g) ?? [];
    });

    expect(anchors.length).toBeGreaterThan(10);
    for (const anchor of anchors) {
      expect(anchor).toContain('target="_blank"');
      expect(anchor).toMatch(/rel="[^"]*noopener[^"]*"/);
      expect(anchor).toMatch(/rel="[^"]*noreferrer[^"]*"/);
    }
  });
});
