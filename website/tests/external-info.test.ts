import { describe, expect, it } from 'vitest';

import type { ExternalInfo } from '../src/atlas/contracts';
import {
  externalInfoDownloadFilename,
  externalInfoDownloadText,
} from '../src/atlas/external-info';

const info = {
  query: {
    dataset: 'gnomad_r4',
    normalized_variant_id: 'chr11-5227002-T-A',
  },
  record: {
    alt: 'A',
    canonical_consequence: null,
    chrom: '11',
    exome: null,
    genome: null,
    joint: { ac: 4, af: 0.04, an: 100 },
    pos: 5_227_002,
    ref: 'T',
    rsids: ['rs334'],
    source_url: 'https://gnomad.broadinstitute.org/variant/11-5227002-T-A',
  },
  retrieved_at: '2026-09-07T00:00:00Z',
  schema_version: 1,
  source: 'gnomad',
  source_release: 'gnomad_r4',
} satisfies ExternalInfo;

describe('external information downloads', () => {
  it('uses the stable variant, source, and release in the filename', () => {
    expect(externalInfoDownloadFilename(info)).toBe(
      'chr11-5227002-T-A.gnomad.gnomad_r4.json',
    );
  });

  it('exports the exact validated response shown by the panel', () => {
    expect(externalInfoDownloadText(info)).toBe(
      `${JSON.stringify(info, null, 2)}\n`,
    );
  });
});
