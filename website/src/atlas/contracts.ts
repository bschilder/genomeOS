/** Strict static-atlas browser contracts for Atlas design §11. */

import { z } from 'zod';

const finiteNumber = z
  .number()
  .refine(Number.isFinite, 'number must be finite');
const probability = finiteNumber.min(0).max(1);
const nonEmpty = z.string().trim().min(1);
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);

export const supportSchema = z.enum([
  'observed',
  'interpolated',
  'prior_dominated',
  'unknown',
]);

const domainSchema = z
  .tuple([finiteNumber, finiteNumber])
  .refine(([lower, upper]) => lower <= upper, 'domain must be ordered');

export const metricDomainsSchema = z.strictObject({
  post_mean: domainSchema,
  post_sd: domainSchema,
});

const artifactIdentityFields = {
  artifact_format: z.union([z.literal(1), z.literal(2)]),
  data_version: nonEmpty,
  entity_type: z.enum(['variant', 'allele', 'gene', 'phenotype']),
  hf_dataset: nonEmpty,
  hf_revision: nonEmpty,
  id: nonEmpty,
  label: nonEmpty,
  measurement: z.enum([
    'allele_frequency',
    'carrier_frequency',
    'phenotype_frequency',
  ]),
  metric_domains: metricDomainsSchema,
  model_version: nonEmpty,
  registry_version: nonEmpty,
  resolution: z.int().min(0).max(15),
  variant_id: nonEmpty,
  target_grid_source: nonEmpty.optional(),
  target_grid_version: nonEmpty.optional(),
};

function requireFormat2TargetGrid(
  value: {
    artifact_format: 1 | 2;
    target_grid_source?: string;
    target_grid_version?: string;
  },
  context: z.RefinementCtx,
): void {
  if (
    value.artifact_format === 2 &&
    (!value.target_grid_source || !value.target_grid_version)
  ) {
    context.addIssue({
      code: 'custom',
      message: 'artifact format 2 requires target-grid source and version',
    });
  }
}

export const artifactIdentitySchema = z
  .strictObject(artifactIdentityFields)
  .superRefine(requireFormat2TargetGrid);

const supportCountsSchema = z.partialRecord(
  supportSchema,
  z.int().nonnegative(),
);

const downloadRefSchema = z.strictObject({
  label: nonEmpty,
  media_type: nonEmpty,
  sha256,
  url: nonEmpty,
});

const externalResourceSchema = z.discriminatedUnion('source', [
  z.strictObject({
    cache_sha256: sha256,
    cache_url: nonEmpty,
    dataset: nonEmpty,
    normalized_variant_id: z
      .string()
      .regex(/^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|MT)-[1-9][0-9]*-[ACGT]+-[ACGT]+$/),
    source: z.literal('gnomad'),
  }),
  z.strictObject({
    cache_sha256: sha256,
    cache_url: nonEmpty,
    normalized_variant_id: z
      .string()
      .regex(/^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|MT)-[1-9][0-9]*-[ACGT]+-[ACGT]+$/),
    rsid: z.string().regex(/^rs[1-9][0-9]*$/),
    source: z.literal('dbsnp'),
  }),
]);

const discoveryReferenceSchema = z.strictObject({
  label: nonEmpty,
  url: z.url(),
});

export const discoveryGroupSchema = z.strictObject({
  biology: nonEmpty,
  id: nonEmpty,
  label: nonEmpty,
  references: z.array(discoveryReferenceSchema).min(1),
  summary: nonEmpty,
});

export const artifactDiscoverySchema = z.strictObject({
  aliases: z.array(nonEmpty).min(1),
  group_id: nonEmpty,
  map_measures: nonEmpty,
  references: z.array(discoveryReferenceSchema).min(1),
  relevance: nonEmpty,
  symbol_expansion: nonEmpty,
});

const artifactRefBaseFields = {
  assumptions: z.array(nonEmpty),
  correlation_range_km: finiteNumber.positive(),
  discovery: artifactDiscoverySchema,
  downloads: z.strictObject({
    manifest: downloadRefSchema,
    observations: downloadRefSchema.nullable(),
    surface: downloadRefSchema,
  }),
  external_resources: z.array(externalResourceSchema),
  likelihood: nonEmpty,
  n_cells: z.int().positive(),
  n_observations: z.int().nonnegative(),
  support_counts: supportCountsSchema,
  surface_sha256: sha256,
  surface_url: nonEmpty,
};

export const artifactRefSchema = z
  .discriminatedUnion('observations_available', [
    z.strictObject({
      ...artifactIdentityFields,
      ...artifactRefBaseFields,
      observations_available: z.literal(true),
      observations_sha256: sha256,
      observations_url: nonEmpty,
    }),
    z.strictObject({
      ...artifactIdentityFields,
      ...artifactRefBaseFields,
      observations_available: z.literal(false),
      observations_sha256: z.null(),
      observations_url: z.null(),
    }),
  ])
  .superRefine((value, context) => {
    requireFormat2TargetGrid(value, context);
    if (
      (value.downloads.observations === null) !==
      !value.observations_available
    ) {
      context.addIssue({
        code: 'custom',
        message: 'observation download must match observations_available',
      });
    }
    for (const resource of value.external_resources) {
      if (
        value.entity_type !== 'variant' ||
        resource.normalized_variant_id !== value.variant_id
      ) {
        context.addIssue({
          code: 'custom',
          message:
            "external lookup requires the artifact's verified variant identity",
        });
      }
    }
  });

export const contextSourceSchema = z.strictObject({
  id: nonEmpty,
  label: nonEmpty,
  license: nonEmpty,
  revision: nonEmpty,
  source_url: z.url(),
  url: nonEmpty,
});

export const atlasCatalogSchema = z
  .strictObject({
    artifact_version: nonEmpty,
    artifacts: z.array(artifactRefSchema).min(1),
    assumptions: z.array(nonEmpty),
    context_sources: z.array(contextSourceSchema),
    created_at: nonEmpty,
    discovery_groups: z.array(discoveryGroupSchema).min(1),
    hf_dataset: nonEmpty,
    hf_revision: nonEmpty,
    registry_versions: z.array(nonEmpty).min(1),
    schema_version: z.literal(1),
  })
  .superRefine(({ artifacts, discovery_groups }, context) => {
    const groupIds = new Set(discovery_groups.map(({ id }) => id));
    if (groupIds.size !== discovery_groups.length) {
      context.addIssue({
        code: 'custom',
        message: 'discovery group ids must be unique',
        path: ['discovery_groups'],
      });
    }
    for (const [index, artifact] of artifacts.entries()) {
      if (!groupIds.has(artifact.discovery.group_id)) {
        context.addIssue({
          code: 'custom',
          message: 'artifact must reference a known discovery group',
          path: ['artifacts', index, 'discovery', 'group_id'],
        });
      }
    }
  });

export const surfaceCellSchema = z
  .strictObject({
    dist_nearest_obs_km: finiteNumber.nonnegative(),
    h3_index: z.string().regex(/^[0-9a-f]{15}$/),
    post_mean: probability,
    post_sd: finiteNumber.nonnegative(),
    // This is posterior SD / prior SD, not a probability. Ratios above one
    // legitimately report a posterior that is less certain than its prior.
    posterior_contraction: finiteNumber.nonnegative(),
    q025: probability,
    q975: probability,
    support: supportSchema,
  })
  .refine(
    ({ post_mean, q025, q975 }) => q025 <= post_mean && post_mean <= q975,
    'q025 <= post_mean <= q975 is required',
  );

export const surfaceArtifactSchema = z.strictObject({
  artifact: artifactIdentitySchema,
  cells: z.array(surfaceCellSchema).min(1),
  schema_version: z.literal(1),
});

export const observationSchema = z
  .strictObject({
    ac: z.int().nonnegative(),
    an: z.int().positive(),
    assay: nonEmpty,
    citation_text: nonEmpty,
    cohort_id: nonEmpty,
    disease_ascertainment_excluded: z.boolean(),
    ingest_version: nonEmpty,
    lat: finiteNumber.min(-90).max(90),
    lon: finiteNumber.min(-180).max(180),
    population_label: nonEmpty,
    radius_km: finiteNumber.positive(),
    sampling_design: nonEmpty,
    source_locator: nonEmpty,
    source_record_id: nonEmpty,
    source_url: z.url(),
    study_id: nonEmpty,
    study_label: nonEmpty,
  })
  .refine(({ ac, an }) => ac <= an, 'ac must not exceed an');

export const observationArtifactSchema = z.strictObject({
  artifact: artifactIdentitySchema,
  observations: z.array(observationSchema),
  schema_version: z.literal(1),
});

const externalFrequencySchema = z.strictObject({
  ac: z.int().nonnegative(),
  ac_hemi: z.int().nonnegative().optional(),
  ac_hom: z.int().nonnegative().optional(),
  af: probability,
  an: z.int().positive(),
});

const ancestryGroupFrequencySchema = z
  .strictObject({
    ac: z.int().nonnegative(),
    af: probability,
    an: z.int().positive(),
    hemizygote_count: z.int().nonnegative(),
    homozygote_count: z.int().nonnegative(),
    id: z.enum([
      'afr',
      'ami',
      'amr',
      'asj',
      'eas',
      'fin',
      'mid',
      'nfe',
      'remaining',
      'sas',
    ]),
    label: nonEmpty,
  })
  .refine(({ ac, an }) => ac <= an, 'ac must not exceed an');

const genomicConstraintSchema = z
  .strictObject({
    chrom: nonEmpty,
    dataset_release: z.literal('gnomAD v3.1.2'),
    expected: z.number().positive(),
    observed: z.int().nonnegative(),
    oe: z.number().nonnegative(),
    possible: z.int().positive(),
    start: z.int().nonnegative(),
    stop: z.int().positive(),
    z: z.number().min(-10).max(10),
  })
  .refine(({ observed, possible }) => observed <= possible, {
    message: 'observed must not exceed possible',
    path: ['observed'],
  })
  .refine(({ start, stop }) => start < stop, {
    message: 'start must be before stop',
    path: ['stop'],
  });

const clinvarEvidenceSchema = z.strictObject({
  clinical_significance: nonEmpty,
  conditions: z.array(
    z.strictObject({
      classifications: z.array(nonEmpty).min(1),
      medgen_id: nonEmpty.nullable(),
      name: nonEmpty,
      submission_count: z.int().positive(),
    }),
  ),
  gold_stars: z.int().min(0).max(4),
  last_evaluated: nonEmpty.nullable(),
  release_date: nonEmpty,
  review_status: nonEmpty,
  submission_count: z.int().nonnegative(),
  variation_id: nonEmpty,
});

const externalBaseSchema = {
  retrieved_at: nonEmpty,
  source_release: nonEmpty,
};

export const externalInfoSchema = z.discriminatedUnion('source', [
  z.strictObject({
    ...externalBaseSchema,
    schema_version: z.literal(2),
    query: z.strictObject({
      dataset: nonEmpty,
      normalized_variant_id: nonEmpty,
    }),
    record: z.strictObject({
      alt: nonEmpty,
      canonical_consequence: z
        .strictObject({
          gene_id: nonEmpty.nullable(),
          gene_symbol: nonEmpty.nullable(),
          hgvsc: nonEmpty.nullable(),
          hgvsp: nonEmpty.nullable(),
          is_canonical: z.boolean().nullable(),
          is_mane_select: z.boolean().nullable(),
          major_consequence: nonEmpty.nullable(),
          transcript_id: nonEmpty.nullable(),
        })
        .nullable(),
      clinvar: clinvarEvidenceSchema.nullable(),
      chrom: nonEmpty,
      exome: externalFrequencySchema.nullable(),
      genetic_ancestry_group_frequencies: z.array(ancestryGroupFrequencySchema),
      genome: externalFrequencySchema.nullable(),
      genomic_constraint: genomicConstraintSchema.nullable(),
      joint: externalFrequencySchema.nullable(),
      pos: z.int().positive(),
      ref: nonEmpty,
      rsids: z.array(nonEmpty),
      source_url: z.url(),
    }),
    source: z.literal('gnomad'),
  }),
  z.strictObject({
    ...externalBaseSchema,
    schema_version: z.literal(1),
    query: z.strictObject({
      normalized_variant_id: nonEmpty,
      rsid: z.string().regex(/^rs[1-9][0-9]*$/),
    }),
    record: z.strictObject({
      citation_count: z.int().nonnegative(),
      hgvs: nonEmpty,
      last_update_date: nonEmpty,
      rsid: z.string().regex(/^rs[1-9][0-9]*$/),
      source_url: z.url(),
      spdi: z.strictObject({
        deleted_sequence: nonEmpty,
        inserted_sequence: nonEmpty,
        position: z.int().nonnegative(),
        seq_id: nonEmpty,
      }),
    }),
    source: z.literal('dbsnp'),
  }),
]);

export type Support = z.infer<typeof supportSchema>;
export type ArtifactIdentity = z.infer<typeof artifactIdentitySchema>;
export type ArtifactRef = z.infer<typeof artifactRefSchema>;
export type AtlasCatalog = z.infer<typeof atlasCatalogSchema>;
export type DiscoveryGroup = z.infer<typeof discoveryGroupSchema>;
export type SurfaceCell = z.infer<typeof surfaceCellSchema>;
export type SurfaceArtifact = z.infer<typeof surfaceArtifactSchema>;
export type Observation = z.infer<typeof observationSchema>;
export type ObservationArtifact = z.infer<typeof observationArtifactSchema>;
export type ExternalResource = z.infer<typeof externalResourceSchema>;
export type ExternalInfo = z.infer<typeof externalInfoSchema>;
