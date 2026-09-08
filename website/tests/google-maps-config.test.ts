import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const repositoryRoot = path.resolve(import.meta.dirname, '../..');
const polygonPage = readFileSync(
  path.join(repositoryRoot, 'website/src/pages/app/polygon.astro'),
  'utf8',
);
const pagesWorkflow = readFileSync(
  path.join(repositoryRoot, '.github/workflows/pages.yml'),
  'utf8',
);
const environmentExample = readFileSync(
  path.join(repositoryRoot, '.env.example'),
  'utf8',
);

describe('Google Maps browser-token wiring', () => {
  it('uses the provisioned GOOGLE_MAPS_TOKEN name at every build boundary', () => {
    expect(polygonPage).toContain('process.env.GOOGLE_MAPS_TOKEN');
    expect(pagesWorkflow).toContain(
      'GOOGLE_MAPS_TOKEN: ${{ secrets.GOOGLE_MAPS_TOKEN }}',
    );
    expect(environmentExample).toContain('GOOGLE_MAPS_TOKEN=');
    expect(
      `${polygonPage}\n${pagesWorkflow}\n${environmentExample}`,
    ).not.toContain('GOOGLE_MAPS_API_KEY');
  });
});
