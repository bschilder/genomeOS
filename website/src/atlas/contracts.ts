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

export const artifactIdentitySchema = z.strictObject({
  artifact_format: z.literal(1),
  data_version: nonEmpty,
  entity_type: z.enum(['variant', 'phenotype']),
  hf_dataset: nonEmpty,
  hf_revision: nonEmpty,
  id: nonEmpty,
  label: nonEmpty,
  measurement: z.enum(['allele_frequency', 'phenotype_frequency']),
  metric_domains: metricDomainsSchema,
  model_version: nonEmpty,
  registry_version: nonEmpty,
  resolution: z.int().min(0).max(15),
  variant_id: nonEmpty,
});

const supportCountsSchema = z.partialRecord(
  supportSchema,
  z.int().nonnegative(),
);

export const artifactRefSchema = artifactIdentitySchema.extend({
  assumptions: z.array(nonEmpty),
  correlation_range_km: finiteNumber.positive(),
  likelihood: nonEmpty,
  n_cells: z.int().positive(),
  n_observations: z.int().nonnegative(),
  observations_sha256: sha256,
  observations_url: nonEmpty,
  support_counts: supportCountsSchema,
  surface_sha256: sha256,
  surface_url: nonEmpty,
});

export const contextSourceSchema = z.strictObject({
  id: nonEmpty,
  label: nonEmpty,
  license: nonEmpty,
  revision: nonEmpty,
  source_url: z.url(),
  url: nonEmpty,
});

export const atlasCatalogSchema = z.strictObject({
  artifact_version: nonEmpty,
  artifacts: z.array(artifactRefSchema).min(1),
  assumptions: z.array(nonEmpty),
  context_sources: z.array(contextSourceSchema),
  created_at: nonEmpty,
  hf_dataset: nonEmpty,
  hf_revision: nonEmpty,
  registry_version: nonEmpty,
  schema_version: z.literal(1),
});

export const surfaceCellSchema = z
  .strictObject({
    dist_nearest_obs_km: finiteNumber.nonnegative(),
    h3_index: z.string().regex(/^[0-9a-f]{15}$/),
    post_mean: probability,
    post_sd: finiteNumber.nonnegative(),
    posterior_contraction: probability,
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
  })
  .refine(({ ac, an }) => ac <= an, 'ac must not exceed an');

export const observationArtifactSchema = z.strictObject({
  artifact: artifactIdentitySchema,
  observations: z.array(observationSchema),
  schema_version: z.literal(1),
});

export type Support = z.infer<typeof supportSchema>;
export type ArtifactIdentity = z.infer<typeof artifactIdentitySchema>;
export type ArtifactRef = z.infer<typeof artifactRefSchema>;
export type AtlasCatalog = z.infer<typeof atlasCatalogSchema>;
export type SurfaceCell = z.infer<typeof surfaceCellSchema>;
export type SurfaceArtifact = z.infer<typeof surfaceArtifactSchema>;
export type Observation = z.infer<typeof observationSchema>;
export type ObservationArtifact = z.infer<typeof observationArtifactSchema>;
