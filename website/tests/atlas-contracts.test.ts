import { describe, expect, it } from 'vitest';

import {
  atlasCatalogSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
} from '../src/atlas/contracts';

const artifact = {
  artifact_format: 1,
  data_version: 'map-2026-08',
  entity_type: 'variant',
  hf_dataset: 'bschilder/genomeos-data',
  hf_revision: 'fc17bc1c1d96a0d0766746dcf26277ccdc669717',
  id: 'hbs-rs334',
  label: 'HbS (rs334)',
  measurement: 'allele_frequency',
  metric_domains: { post_mean: [0.01, 0.2], post_sd: [0.001, 0.08] },
  model_version: 'v1',
  registry_version: 'map-survey-coordinates-v1',
  resolution: 3,
  variant_id: 'chr11-5227002-T-A',
};

const cell = {
  dist_nearest_obs_km: 25,
  h3_index: '83754efffffffff',
  post_mean: 0.08,
  post_sd: 0.02,
  posterior_contraction: 0.7,
  q025: 0.04,
  q975: 0.12,
  support: 'observed',
};

const observation = {
  ac: 4,
  an: 100,
  assay: 'genotype',
  citation_text: 'Example publication.',
  cohort_id: 'map-study-1',
  disease_ascertainment_excluded: true,
  ingest_version: 'map-2026-08',
  lat: 40.7,
  lon: -74,
  population_label: 'Example population',
  radius_km: 12,
  sampling_design: 'population_random',
  source_locator: 'MAP survey 1',
  source_record_id: 'map-surveys:1',
  source_url: 'https://example.org/source',
};

describe('atlas browser contracts', () => {
  it('does not invent support or an observation radius', () => {
    const { support: _support, ...surfaceWithoutSupport } = cell;
    const { radius_km: _radius, ...observationWithoutRadius } = observation;

    expect(() =>
      surfaceArtifactSchema.parse({
        artifact,
        cells: [surfaceWithoutSupport],
        schema_version: 1,
      }),
    ).toThrow();
    expect(() =>
      observationArtifactSchema.parse({
        artifact,
        observations: [observationWithoutRadius],
        schema_version: 1,
      }),
    ).toThrow();
  });

  it('rejects invalid scientific values and unknown support states', () => {
    for (const invalid of [
      { ...cell, support: 'nearby' },
      { ...cell, post_mean: Number.NaN },
      { ...cell, q025: 0.2, q975: 0.1 },
    ]) {
      expect(() =>
        surfaceArtifactSchema.parse({
          artifact,
          cells: [invalid],
          schema_version: 1,
        }),
      ).toThrow();
    }

    for (const invalid of [
      { ...observation, an: 0 },
      { ...observation, lat: 91 },
      { ...observation, lon: 181 },
    ]) {
      expect(() =>
        observationArtifactSchema.parse({
          artifact,
          observations: [invalid],
          schema_version: 1,
        }),
      ).toThrow();
    }
  });

  it('requires the supported schema version, revisions, and checksums', () => {
    const catalogArtifact = {
      ...artifact,
      assumptions: ['fixture'],
      correlation_range_km: 400,
      likelihood: 'beta_binomial',
      n_cells: 1,
      n_observations: 1,
      observations_sha256: 'b'.repeat(64),
      observations_url: 'hbs-rs334.observations.json',
      support_counts: { observed: 1 },
      surface_sha256: 'a'.repeat(64),
      surface_url: 'hbs-rs334.surface.json',
    };
    const catalog = {
      artifact_version: 'v1',
      artifacts: [catalogArtifact],
      assumptions: ['fixture'],
      context_sources: [],
      created_at: '2026-09-06T00:00:00Z',
      hf_dataset: 'bschilder/genomeos-data',
      hf_revision: artifact.hf_revision,
      registry_version: artifact.registry_version,
      schema_version: 1,
    };

    expect(atlasCatalogSchema.parse(catalog).artifacts).toHaveLength(1);
    expect(() =>
      atlasCatalogSchema.parse({ ...catalog, schema_version: 2 }),
    ).toThrow();
    expect(() =>
      atlasCatalogSchema.parse({
        ...catalog,
        artifacts: [{ ...catalogArtifact, hf_revision: '' }],
      }),
    ).toThrow();
    expect(() =>
      atlasCatalogSchema.parse({
        ...catalog,
        artifacts: [{ ...catalogArtifact, surface_sha256: undefined }],
      }),
    ).toThrow();
  });
});
