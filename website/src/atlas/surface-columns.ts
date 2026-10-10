/**
 * Columnar surface model for Atlas design §11 and fast-load design §B.2, §B.6.4. Two accessors make
 * the precision rule a type guarantee: `renderAt` (float32 render tier) drives colour, height and
 * anchors; `cellAt` (float64 detail tier) is the only source of displayed numbers.
 */

import { splitLongToH3Index } from 'h3-js';

import type { ArtifactIdentity, Support, SurfaceCell } from './contracts';
import { gridRowOf } from './geometry/topology';
import { SUPPORT_CODES } from './gosa/decode';
import type { DecodedDetail, DecodedGrid } from './gosa/types';

export interface SurfaceArtifact {
  artifactKey: string;
  artifact: ArtifactIdentity;
  detail: DecodedDetail | null;
  grid: DecodedGrid;
  support: Uint8Array<ArrayBuffer>;
  values: {
    post_mean: Float32Array<ArrayBuffer>;
    post_sd: Float32Array<ArrayBuffer>;
  };
}

export type RenderCell = {
  h3: string;
  post_mean: number;
  post_sd: number;
  support: Support;
};

export class DetailNotLoadedError extends Error {
  readonly artifactKey: string;

  constructor(artifactKey: string) {
    super(`Cell values for ${artifactKey} are not loaded yet`);
    this.name = 'DetailNotLoadedError';
    this.artifactKey = artifactKey;
  }
}

export function artifactKeyFor(
  ref: Pick<ArtifactIdentity, 'data_version' | 'id' | 'model_version'>,
): string {
  return `${ref.id}:${ref.model_version}:${ref.data_version}`;
}

function requireRow(surface: SurfaceArtifact, row: number): void {
  if (!Number.isInteger(row) || row < 0 || row >= surface.grid.n) {
    throw new RangeError(
      `Row ${row} is outside ${surface.artifactKey} (${surface.grid.n} cells)`,
    );
  }
}

export function h3At(surface: SurfaceArtifact, row: number): string {
  requireRow(surface, row);
  return splitLongToH3Index(surface.grid.h3Lo[row], surface.grid.h3Hi[row]);
}

/** Binary search over the sorted two-lane u64 grid (`gridRowOf`); null for text that is not an H3
 * index or a cell that is not in it. */
export function rowForH3(surface: SurfaceArtifact, h3: string): number | null {
  if (!/^[0-9a-f]{15,16}$/.test(h3)) return null;
  return gridRowOf(surface.grid, h3);
}

export function renderAt(surface: SurfaceArtifact, row: number): RenderCell {
  requireRow(surface, row);
  return {
    h3: h3At(surface, row),
    post_mean: surface.values.post_mean[row],
    post_sd: surface.values.post_sd[row],
    support: SUPPORT_CODES[surface.support[row]],
  };
}

export function cellAt(surface: SurfaceArtifact, row: number): SurfaceCell {
  requireRow(surface, row);
  const detail = surface.detail;
  if (!detail) throw new DetailNotLoadedError(surface.artifactKey);
  return {
    dist_nearest_obs_km: detail.dist_nearest_obs_km[row],
    h3_index: h3At(surface, row),
    post_mean: detail.post_mean[row],
    post_sd: detail.post_sd[row],
    posterior_contraction: detail.posterior_contraction[row],
    q025: detail.q025[row],
    q975: detail.q975[row],
    support: SUPPORT_CODES[surface.support[row]],
  };
}
