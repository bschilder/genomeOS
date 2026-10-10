/** Support materials for masked cells (Atlas design §11; Cesium explorer design §8.4).
 *
 * `unknown` cells draw a neutral hatch; `prior_dominated` cells draw dots in
 * their palette-bin colour. Geometry comes from the data worker (spec
 * 2026-10-07 §B.6.5); only the materials live here.
 */

import { Cartesian2, Color, Material } from 'cesium';

import type { Support } from '../contracts';

export function materialForSupport(
  support: Extract<Support, 'unknown' | 'prior_dominated'>,
  paletteColor?: string,
): Material {
  if (support === 'unknown') {
    return Material.fromType('Grid', {
      cellAlpha: 0.24,
      color: Color.fromCssColorString('#a8b5c9').withAlpha(0.72),
      lineCount: new Cartesian2(5, 5),
      lineThickness: new Cartesian2(1.65, 1.65),
    });
  }
  if (!paletteColor)
    throw new Error('prior-dominated cells require their palette color');
  const base = Color.fromCssColorString(paletteColor);
  const highlight = Color.lerp(base, Color.WHITE, 0.38, new Color());
  return Material.fromType('Dot', {
    darkColor: base.withAlpha(0.46),
    lightColor: highlight.withAlpha(0.82),
    repeat: new Cartesian2(10, 10),
  });
}
