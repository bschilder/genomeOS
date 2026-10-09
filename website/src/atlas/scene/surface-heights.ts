/** Render-tier height lookups for markers and highlights (Atlas design §11; spec 2026-10-07 §B.2).
 *
 * Heights always come from the f32 render tier through `renderAt`, never from
 * the f64 detail tier, so highlights and observation markers stay
 * bit-consistent with the worker-built mesh whether or not cell values have
 * loaded.
 */

import { latLngToCell } from 'h3-js';

import { renderAt, rowForH3, type SurfaceArtifact } from '../surface-columns';
import { heightFor, type Metric } from '../visual-encoding';

export interface SurfaceHeightSource {
  readonly artifactKey: string | null;
  readonly resolution: number;
  /** Cell-top height in metres at exaggeration 1; null when the cell is outside the surface. */
  cellHeight(h3Index: string, metric: Metric): number | null;
}

export function columnarHeightSource(
  surface: SurfaceArtifact,
): SurfaceHeightSource {
  return {
    artifactKey: surface.artifactKey,
    resolution: surface.artifact.resolution,
    cellHeight(h3Index, metric) {
      const row = rowForH3(surface, h3Index);
      if (row === null) return null;
      const cell = renderAt(surface, row);
      return heightFor(
        cell.support,
        cell[metric],
        surface.artifact.metric_domains[metric],
        1,
      );
    },
  };
}

export function surfaceHeightAt(
  point: { lat: number; lon: number },
  source: SurfaceHeightSource,
  metric: Metric,
  elevation: boolean,
  exaggeration: number,
): number {
  if (!elevation) return 0;
  const height = source.cellHeight(
    latLngToCell(point.lat, point.lon, source.resolution),
    metric,
  );
  return height === null ? 0 : height * Math.max(0, exaggeration);
}
