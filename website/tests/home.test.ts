import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const homepage = path.resolve(import.meta.dirname, '../dist/index.html');
const html = existsSync(homepage) ? readFileSync(homepage, 'utf8') : '';

describe('homepage contract', () => {
  it('leads with the public-good mission and current evidence scale', () => {
    expect(html).toMatch(/<h1[^>]*>Explore genomes across the world\.<\/h1>/);
    expect(html).toMatch(/open source/i);
    expect(html).toMatch(/global community/i);
    expect(html).toMatch(/public good/i);
    expect(html).toMatch(/4,392[\s\S]*6\.69M[\s\S]*disease/);
  });

  it('introduces the mission before explaining the delivery process', () => {
    expect(html).toMatch(
      /Why genomeOS[\s\S]*Built in the open[\s\S]*Potential applications[\s\S]*How genomeOS works[\s\S]*Aggregate the evidence[\s\S]*Model what the evidence supports[\s\S]*Open it to the world/,
    );
  });

  it('uses accessible illustrations to guide the multi-scale vision', () => {
    expect(html).toContain('/images/vision-earth.webp');
    expect(html).toContain('/images/vision-cell.webp');
    expect(html).toContain('/images/vision-bridge.webp');
    expect(html).toContain('alt="A luminous globe showing genetic evidence');
    expect(html).toContain('alt="A visual journey from a cell nucleus');
    expect(html).toContain(
      'alt="Folded chromatin and a highlighted gene connected',
    );
  });

  it('makes the GitHub community entry points prominent', () => {
    expect(html).toContain(
      'https://github.com/bschilder/genomeOS/discussions/76',
    );
    expect(html).toContain('https://github.com/bschilder/genomeOS/issues');
    expect(html).toContain('https://github.com/users/bschilder/projects/8');
    expect(
      html.match(/class="[^"]*github-cta/g)?.length ?? 0,
    ).toBeGreaterThanOrEqual(6);
  });

  it('offers keyboard bypass and an accessible repository link', () => {
    expect(html).toContain('Skip to main content');
    expect(html).toContain('aria-label="View genomeOS on GitHub"');
    expect(html).toContain('https://github.com/bschilder/genomeOS');
  });
});
