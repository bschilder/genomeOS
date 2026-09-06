import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const dist = path.resolve(import.meta.dirname, '../dist');
const guides = [
  'docs',
  'docs/system-overview',
  'docs/scientific-safeguards',
  'docs/data-and-literature',
  'docs/modeling-and-validation',
  'docs/issues-and-projects',
  'docs/local-development',
  'docs/deployment',
];

function read(relativePath: string): string {
  const filename = path.join(dist, relativePath);
  return existsSync(filename) ? readFileSync(filename, 'utf8') : '';
}

describe('technical documentation routes', () => {
  it.each(guides)('builds /%s/', (guide) => {
    expect(read(path.join(guide, 'index.html'))).not.toBe('');
  });

  it('connects P0–P5 summaries to authoritative repository documents', () => {
    const html = read('docs/index.html');
    expect(html).toContain('P0');
    expect(html).toContain('P5');
    expect(html).toContain('docs/overview.md');
    expect(html).toContain('docs/scientific-engineering-objectives.md');
    expect(html).toContain('2026-08-22-genome-os-atlas-v1-design.md');
  });

  it('offers clear recovery routes from the custom 404', () => {
    const html = read('404.html');
    expect(html).toContain('That route is outside the atlas.');
    expect(html).toContain('href="/"');
    expect(html).toContain('href="/contribute/"');
    expect(html).toContain('href="/docs/"');
  });
});
