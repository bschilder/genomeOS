/**
 * A build without PUBLIC_GA_MEASUREMENT_ID loads no analytics (#422). The unit-test build
 * (tests/setup/build.ts) clears the variable, as local dev, the fallback build and forks do.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const dist = path.resolve(import.meta.dirname, '../dist');
const TEXT = /\.(?:css|html|js|json|mjs|svg|txt|webmanifest|xml)$/;

function textFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return textFiles(target);
    return TEXT.test(entry.name) ? [target] : [];
  });
}

const read = (route: string) =>
  readFileSync(path.join(dist, route, 'index.html'), 'utf8');

describe('a build without a Measurement ID', () => {
  it('names neither gtag nor its loader in any emitted file', () => {
    expect(existsSync(path.join(dist, 'app/index.html'))).toBe(true);
    const files = textFiles(dist);
    expect(files.length).toBeGreaterThan(50);
    const offenders = files
      .filter((file) =>
        /gtag|googletagmanager/.test(readFileSync(file, 'utf8')),
      )
      .map((file) => path.relative(dist, file));
    expect(offenders).toEqual([]);
  });

  it('renders no cookie control, docked icon or Cookie settings link', () => {
    // Markup only: the control's stylesheet may still name these attributes in selectors.
    const element =
      /<[a-z]+\b[^>]*\sdata-cookie-(?:control|dock|settings|toggle)\b/;
    for (const route of ['', 'app', 'app/polygon', 'docs', 'privacy'])
      expect(read(route), route).not.toMatch(element);
  });

  it('ships none of the cookie control code', () => {
    const offenders = textFiles(dist)
      .filter((file) => /\.(?:html|js|mjs)$/.test(file))
      .filter((file) =>
        /genomeos-analytics-consent|Europe\/Vaduz|globalPrivacyControl/.test(
          readFileSync(file, 'utf8'),
        ),
      )
      .map((file) => path.relative(dist, file));
    expect(offenders).toEqual([]);
  });

  it('still publishes the privacy page, linked from the site and docs footers', () => {
    expect(read('privacy')).toContain('<h1>');
    for (const route of ['', 'contribute', 'docs', 'docs/deployment'])
      expect(read(route), route).toMatch(
        /<nav[^>]*aria-label="Site policies"[^>]*>\s*<a[^>]*href="\/privacy\/"/,
      );
  });
});
