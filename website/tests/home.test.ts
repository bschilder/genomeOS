import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const homepage = path.resolve(import.meta.dirname, '../dist/index.html');
const html = existsSync(homepage) ? readFileSync(homepage, 'utf8') : '';

describe('homepage contract', () => {
  it('explains the primary claim and evidence distinction', () => {
    expect(html).toMatch(/<h1[^>]*>Explore genomes across the world\.<\/h1>/);
    expect(html).toMatch(
      /Measured here[\s\S]*Estimated there[\s\S]*Never confused/,
    );
  });

  it('offers keyboard bypass and an accessible repository link', () => {
    expect(html).toContain('Skip to main content');
    expect(html).toContain('aria-label="View genomeOS on GitHub"');
    expect(html).toContain('https://github.com/bschilder/genomeOS');
  });
});
