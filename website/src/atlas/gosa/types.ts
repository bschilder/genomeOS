/** Decoded GOSA tiers as transferable typed arrays (Atlas design §11; fast-load design §B.2, §B.6.4). */

import type { ArtifactIdentity } from '../contracts';

/** The shared sorted grid as two u32 lanes of each u64 H3 index. */
export interface DecodedGrid {
  gridSha256: string;
  h3Hi: Uint32Array<ArrayBuffer>;
  h3Lo: Uint32Array<ArrayBuffer>;
  n: number;
  resolution: number;
}

/** Render tier: colour, height and bins only; never displayed as numbers. */
export interface DecodedRender {
  artifact: ArtifactIdentity;
  post_mean: Float32Array<ArrayBuffer>;
  post_sd: Float32Array<ArrayBuffer>;
  support: Uint8Array<ArrayBuffer>;
}

/** Detail tier: every displayed number, bit-identical to the published artifact. */
export interface DecodedDetail {
  dist_nearest_obs_km: Float64Array<ArrayBuffer>;
  post_mean: Float64Array<ArrayBuffer>;
  post_sd: Float64Array<ArrayBuffer>;
  posterior_contraction: Float64Array<ArrayBuffer>;
  q025: Float64Array<ArrayBuffer>;
  q975: Float64Array<ArrayBuffer>;
}
