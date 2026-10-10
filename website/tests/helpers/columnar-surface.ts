import { getResolution } from 'h3-js';

import type { ArtifactIdentity, Support } from '../../src/atlas/contracts';
import { SUPPORT_CODES } from '../../src/atlas/gosa/decode';
import type { DecodedDetail } from '../../src/atlas/gosa/types';
import {
  artifactKeyFor,
  type SurfaceArtifact,
} from '../../src/atlas/surface-columns';

export interface FixtureCell {
  h3: string;
  support: Support;
  post_mean: number;
  post_sd: number;
}

function sortedByIndex(cells: readonly FixtureCell[]): FixtureCell[] {
  return [...cells].sort((first, second) => {
    const left = BigInt(`0x${first.h3}`);
    const right = BigInt(`0x${second.h3}`);
    return left < right ? -1 : left > right ? 1 : 0;
  });
}

function detailFor(cells: readonly FixtureCell[]): DecodedDetail {
  return {
    dist_nearest_obs_km: Float64Array.from(cells, () => 42.4),
    post_mean: Float64Array.from(cells, ({ post_mean }) => post_mean),
    post_sd: Float64Array.from(cells, ({ post_sd }) => post_sd),
    posterior_contraction: Float64Array.from(cells, () => 0.5),
    q025: Float64Array.from(cells, ({ post_mean }) =>
      Math.max(0, post_mean - 0.05),
    ),
    q975: Float64Array.from(cells, ({ post_mean }) =>
      Math.min(1, post_mean + 0.05),
    ),
  };
}

/** A small columnar artifact on a sorted grid, shaped exactly like the provider's. */
export function columnarSurface(
  cells: readonly FixtureCell[],
  options: { id?: string; withDetail?: boolean } = {},
): SurfaceArtifact {
  const sorted = sortedByIndex(cells);
  const resolution = getResolution(sorted[0].h3);
  const h3Lo = new Uint32Array(sorted.length);
  const h3Hi = new Uint32Array(sorted.length);
  sorted.forEach(({ h3 }, row) => {
    const value = BigInt(`0x${h3}`);
    h3Lo[row] = Number(value & 0xffffffffn);
    h3Hi[row] = Number(value >> 32n);
  });
  const artifact = {
    artifact_format: 2,
    data_version: 'map-2026-08',
    entity_type: 'variant',
    hf_dataset: 'bschilder/genomeos-data',
    hf_revision: 'fixture',
    id: options.id ?? 'fixture-artifact',
    label: 'Fixture artifact',
    measurement: 'allele_frequency',
    metric_domains: { post_mean: [0, 1], post_sd: [0, 0.5] },
    model_version: 'v3',
    registry_version: 'fixture-registry',
    resolution,
    target_grid_source: 'fixture-grid',
    target_grid_version: 'fixture-grid-v1',
    variant_id: 'chr11-5227002-t-a',
  } satisfies ArtifactIdentity;
  return {
    artifact,
    artifactKey: artifactKeyFor(artifact),
    detail: options.withDetail ? detailFor(sorted) : null,
    grid: {
      gridSha256: '0'.repeat(64),
      h3Hi,
      h3Lo,
      n: sorted.length,
      resolution,
    },
    support: Uint8Array.from(sorted, ({ support }) =>
      SUPPORT_CODES.indexOf(support),
    ),
    values: {
      post_mean: Float32Array.from(sorted, ({ post_mean }) => post_mean),
      post_sd: Float32Array.from(sorted, ({ post_sd }) => post_sd),
    },
  };
}
