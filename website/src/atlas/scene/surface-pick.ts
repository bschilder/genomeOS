/** Cell resolution for chunk-level surface picks (Atlas design §11; spec 2026-10-07 §B.6.6).
 *
 * Surface and support primitives pick as a whole chunk. The cell under the
 * pointer comes from the ellipsoid at elevation 0 (no extra render pass) or
 * from a translucent depth pick otherwise, scoped to this call because
 * `pickTranslucentDepth` is scene-wide and also drives camera pivots. The
 * incoming group of an unfinished swap is hidden for that one pass so depth
 * always comes from the displayed surface.
 */

import {
  Ellipsoid,
  Math as CesiumMath,
  type Cartesian2,
  type Cartesian3,
  type Scene,
} from 'cesium';

import { resolveSurfaceRow } from '../geometry/pick-resolver';
import { h3At, renderAt, type SurfaceArtifact } from '../surface-columns';
import type { SurfaceGeometry } from '../url-state';
import { heightFor, type Metric } from '../visual-encoding';
import { preferredAtlasPick, type PickResolver } from './picking';
import { SURFACE_CLEARANCE_METRES } from './surface-appearance';

export interface PickTarget {
  artifactKey: string;
  surface: SurfaceArtifact;
  hidden: readonly { show: boolean }[];
}

export interface SurfacePickContext {
  target(): PickTarget | null;
  factor(): number;
  metric(): Metric;
  geometry(): SurfaceGeometry;
}

type DepthPickScene = Pick<
  Scene,
  'camera' | 'pickPosition' | 'pickTranslucentDepth'
>;

export function pickDepthPosition(
  scene: Pick<Scene, 'pickPosition' | 'pickTranslucentDepth'>,
  position: Cartesian2,
  hidden: readonly { show: boolean }[],
): Cartesian3 | undefined {
  const previous = scene.pickTranslucentDepth;
  const shown = hidden.map((collection) => collection.show);
  for (const collection of hidden) collection.show = false;
  scene.pickTranslucentDepth = true;
  try {
    return scene.pickPosition(position) ?? undefined;
  } finally {
    scene.pickTranslucentDepth = previous;
    hidden.forEach((collection, index) => {
      collection.show = shown[index];
    });
  }
}

export function createSurfacePickResolver(
  scene: DepthPickScene,
  context: SurfacePickContext,
): PickResolver {
  return (picks, position) => {
    const target = context.target();
    const chosen = preferredAtlasPick(picks, target?.artifactKey ?? null);
    if (!chosen || chosen.kind === 'surface') return null;
    if (chosen.kind === 'observation') return chosen;
    if (!target) return null;
    const factor = context.factor();
    let cartesian: [number, number, number] | null = null;
    let ellipsoidHit: { lat: number; lon: number } | null = null;
    if (factor === 0) {
      const hit = scene.camera.pickEllipsoid(position, Ellipsoid.WGS84);
      const cartographic = hit
        ? Ellipsoid.WGS84.cartesianToCartographic(hit)
        : undefined;
      if (!cartographic) return null;
      ellipsoidHit = {
        lat: CesiumMath.toDegrees(cartographic.latitude),
        lon: CesiumMath.toDegrees(cartographic.longitude),
      };
    } else {
      const hit = pickDepthPosition(scene, position, target.hidden);
      if (!hit) return null;
      cartesian = [hit.x, hit.y, hit.z];
    }
    const metric = context.metric();
    const domain = target.surface.artifact.metric_domains[metric];
    const row = resolveSurfaceRow(
      {
        cartesian,
        clearance: SURFACE_CLEARANCE_METRES,
        ellipsoidHit,
        factor,
        geometry: context.geometry(),
      },
      target.surface,
      // Heights at exaggeration 1: the resolver applies `factor` itself.
      (candidate) => {
        const cell = renderAt(target.surface, candidate);
        return heightFor(cell.support, cell[metric], domain, 1);
      },
    );
    return row === null
      ? null
      : {
          artifactKey: target.artifactKey,
          h3Index: h3At(target.surface, row),
          kind: 'surface',
          row,
        };
  };
}
