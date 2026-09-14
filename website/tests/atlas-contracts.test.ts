import { describe, expect, it } from 'vitest';

import {
  atlasCatalogSchema,
  externalInfoSchema,
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
  study_id: 'map-study-1',
  study_label: 'Example study',
};

const downloads = {
  manifest: {
    label: 'Artifact manifest',
    media_type: 'application/json',
    sha256: 'c'.repeat(64),
    url: 'hbs-rs334.manifest.json',
  },
  observations: {
    label: 'Measured observations',
    media_type: 'application/json',
    sha256: 'b'.repeat(64),
    url: 'hbs-rs334.observations.json',
  },
  surface: {
    label: 'Inferred surface',
    media_type: 'application/json',
    sha256: 'a'.repeat(64),
    url: 'hbs-rs334.surface.json',
  },
};

const discovery = {
  aliases: ['sickle hemoglobin', 'HBB'],
  group_id: 'red-blood-cell-disorders',
  map_measures: 'Frequency of the HbS allele in sampled populations.',
  references: [
    {
      label: 'MedlinePlus Genetics: sickle cell disease',
      url: 'https://medlineplus.gov/genetics/condition/sickle-cell-disease/',
    },
  ],
  relevance: 'HbS is the causal hemoglobin variant in sickle cell disease.',
  symbol_expansion: 'Hemoglobin S, HBB rs334',
};

const discoveryGroups = [
  {
    biology: 'These maps describe variation affecting red blood cells.',
    id: 'red-blood-cell-disorders',
    label: 'Red blood cell disorders',
    references: [
      {
        label: 'NIH overview',
        url: 'https://www.nhlbi.nih.gov/health/anemia',
      },
    ],
    summary: 'Hemoglobin and red-cell enzyme traits.',
  },
];

describe('atlas browser contracts', () => {
  it('accepts format 3 with target-grid identity and refuses it without provenance', () => {
    const format3 = {
      ...artifact,
      artifact_format: 3,
      target_grid_source: 'worldpop-1km-unconstrained',
      target_grid_version: 'fixture-2020',
    };
    expect(
      surfaceArtifactSchema.parse({
        artifact: format3,
        cells: [cell],
        schema_version: 1,
      }).artifact.artifact_format,
    ).toBe(3);
    expect(() =>
      surfaceArtifactSchema.parse({
        artifact: { ...artifact, artifact_format: 3 },
        cells: [cell],
        schema_version: 1,
      }),
    ).toThrow(/target-grid/);
  });

  it('accepts a complete source-backed observation', () => {
    const parsed = observationArtifactSchema.parse({
      artifact,
      observations: [observation],
      schema_version: 1,
    });
    expect(parsed.observations[0]).toMatchObject({
      study_id: 'map-study-1',
      study_label: 'Example study',
    });
  });

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

  it('accepts posterior-to-prior uncertainty ratios above one', () => {
    const parsed = surfaceArtifactSchema.parse({
      artifact,
      cells: [{ ...cell, posterior_contraction: 1.37 }],
      schema_version: 1,
    });

    expect(parsed.cells[0].posterior_contraction).toBe(1.37);
    expect(() =>
      surfaceArtifactSchema.parse({
        artifact,
        cells: [{ ...cell, posterior_contraction: -0.01 }],
        schema_version: 1,
      }),
    ).toThrow();
  });

  it('validates versioned gnomAD ancestry, constraint, and ClinVar evidence', () => {
    const evidence = {
      query: {
        dataset: 'gnomad_r4',
        normalized_variant_id: 'chr11-5227002-T-A',
      },
      record: {
        alt: 'A',
        canonical_consequence: null,
        chrom: '11',
        clinvar: {
          clinical_significance: 'Pathogenic',
          conditions: [
            {
              classifications: ['Pathogenic'],
              medgen_id: 'C0002895',
              name: 'Hb SS disease',
              submission_count: 2,
            },
          ],
          gold_stars: 2,
          last_evaluated: '2026-02-26',
          release_date: '2026-06-06',
          review_status: 'criteria provided, multiple submitters, no conflicts',
          submission_count: 3,
          variation_id: '15333',
        },
        exome: null,
        genetic_ancestry_group_frequencies: [
          {
            ac: 3707,
            af: 3707 / 74908,
            an: 74908,
            hemizygote_count: 0,
            homozygote_count: 36,
            id: 'afr',
            label: 'African/African American',
          },
        ],
        genome: null,
        genomic_constraint: {
          chrom: 'chr11',
          dataset_release: 'gnomAD v3.1.2',
          expected: 144.25935104346829,
          observed: 151,
          oe: 1.0467259065549284,
          possible: 1722,
          start: 5227000,
          stop: 5228000,
          z: -0.5612155853702537,
        },
        joint: { ac: 4272, af: 4272 / 1610650, an: 1610650 },
        pos: 5227002,
        ref: 'T',
        rsids: ['rs334'],
        source_url:
          'https://gnomad.broadinstitute.org/variant/11-5227002-T-A?dataset=gnomad_r4',
      },
      retrieved_at: '2026-09-08T14:00:00Z',
      schema_version: 2,
      source: 'gnomad',
      source_release: 'gnomad_r4',
    } as const;

    expect(externalInfoSchema.parse(evidence).record).toMatchObject({
      clinvar: { variation_id: '15333' },
      genetic_ancestry_group_frequencies: [{ id: 'afr' }],
      genomic_constraint: { start: 5227000, stop: 5228000 },
    });
    expect(() =>
      externalInfoSchema.parse({ ...evidence, schema_version: 1 }),
    ).toThrow();
    expect(() =>
      externalInfoSchema.parse({
        ...evidence,
        record: {
          ...evidence.record,
          genetic_ancestry_group_frequencies: [
            {
              ...evidence.record.genetic_ancestry_group_frequencies[0],
              ac: 101,
              an: 100,
            },
          ],
        },
      }),
    ).toThrow(/ac must not exceed an/);
    expect(() =>
      externalInfoSchema.parse({
        ...evidence,
        record: {
          ...evidence.record,
          genomic_constraint: {
            ...evidence.record.genomic_constraint,
            z: 10.1,
          },
        },
      }),
    ).toThrow();
  });

  it('requires a source-backed study identity and label', () => {
    const { study_id: _studyId, ...withoutStudyId } = observation;
    const { study_label: _studyLabel, ...withoutStudyLabel } = observation;

    for (const invalid of [
      withoutStudyId,
      withoutStudyLabel,
      { ...observation, study_id: '' },
      { ...observation, study_label: '' },
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
      discovery,
      downloads,
      external_resources: [
        {
          cache_sha256: 'd'.repeat(64),
          cache_url: 'external/gnomad/chr11-5227002-t-a.json',
          dataset: 'gnomad_r4',
          normalized_variant_id: artifact.variant_id,
          source: 'gnomad',
        },
      ],
      likelihood: 'beta_binomial',
      n_cells: 1,
      n_observations: 1,
      observations_available: true,
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
      discovery_groups: discoveryGroups,
      hf_dataset: 'bschilder/genomeos-data',
      hf_revision: artifact.hf_revision,
      registry_versions: [artifact.registry_version],
      schema_version: 1,
    };

    const parsed = atlasCatalogSchema.parse(catalog);
    expect(parsed.artifacts).toHaveLength(1);
    expect(parsed.discovery_groups[0].label).toBe('Red blood cell disorders');
    expect(parsed.artifacts[0].discovery.symbol_expansion).toContain('HBB');
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

  it('distinguishes a reviewed surface-only artifact from an empty observation set', () => {
    const surfaceOnly = {
      ...artifact,
      assumptions: ['AFND observation publication pending corpus rebuild'],
      correlation_range_km: 400,
      discovery,
      downloads: { ...downloads, observations: null },
      entity_type: 'gene',
      external_resources: [],
      likelihood: 'beta_binomial',
      measurement: 'carrier_frequency',
      n_cells: 1,
      n_observations: 233,
      observations_available: false,
      observations_sha256: null,
      observations_url: null,
      support_counts: { observed: 1 },
      surface_sha256: 'a'.repeat(64),
      surface_url: 'kir-2dl1.surface.json',
      variant_id: 'kir:2dl1',
    };
    const catalog = {
      artifact_version: 'v1',
      artifacts: [surfaceOnly],
      assumptions: ['fixture'],
      context_sources: [],
      created_at: '2026-09-06T00:00:00Z',
      discovery_groups: discoveryGroups,
      hf_dataset: 'bschilder/genomeos-data',
      hf_revision: artifact.hf_revision,
      registry_versions: [artifact.registry_version],
      schema_version: 1,
    };

    expect(atlasCatalogSchema.parse(catalog).artifacts[0]).toMatchObject({
      n_observations: 233,
      observations_available: false,
      observations_url: null,
    });
    expect(() =>
      atlasCatalogSchema.parse({
        ...catalog,
        artifacts: [
          {
            ...surfaceOnly,
            observations_available: true,
          },
        ],
      }),
    ).toThrow();
    expect(() =>
      atlasCatalogSchema.parse({
        ...catalog,
        artifacts: [
          {
            ...surfaceOnly,
            external_resources: [
              {
                cache_sha256: 'd'.repeat(64),
                cache_url: 'external/gnomad/kir.json',
                dataset: 'gnomad_r4',
                normalized_variant_id: 'chr11-1-A-C',
                source: 'gnomad',
              },
            ],
          },
        ],
      }),
    ).toThrow(/verified variant identity/);
    expect(() =>
      atlasCatalogSchema.parse({
        ...catalog,
        artifacts: [
          {
            ...surfaceOnly,
            discovery: { ...discovery, group_id: 'missing-group' },
          },
        ],
      }),
    ).toThrow(/known discovery group/);
  });
});
