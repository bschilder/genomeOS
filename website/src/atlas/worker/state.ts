/**
 * Worker-resident decoded tiers keyed per grid and artifact (fast-load design §B.6.3, §B.6.13).
 *
 * The worker never evicts a render tier on its own. The main-thread provider caches every
 * surface it hands out (Task 37 (B2.14)) and does not re-send a render tier on a cache hit, so
 * any eviction here would make a later `build-chunks`, `recolour`, `build-edges` or
 * `context-heights` for that artifact fail until a reload. The worker is a page singleton
 * (`atlasWorker()`), so these maps live exactly as long as the provider's cache. Memory bound:
 * one shared grid plus at most the catalog's 30 render tiers (77,844 cells × 9 bytes ≈ 0.7 MB
 * each, ≈ 21 MB), the same order as the copy the main thread already keeps.
 */

import type { DecodedGrid, DecodedRender } from '../gosa/types';

export interface WorkerState {
  grids: Map<string, DecodedGrid>;
  /** artifactKey -> the grid_sha256 its render tier was decoded against. */
  renderGrids: Map<string, string>;
  renders: Map<string, DecodedRender>;
}

export function createWorkerState(): WorkerState {
  return { grids: new Map(), renderGrids: new Map(), renders: new Map() };
}
