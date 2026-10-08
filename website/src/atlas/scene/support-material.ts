/** Surface batching and support materials for Atlas design §11. */

import { Cartesian2, Color, Material } from 'cesium';

import type { Support, SurfaceCell } from '../contracts';
import {
  colorForCell,
  quantizeMetric,
  type Metric,
  type MetricDomain,
  type PaletteId,
} from '../visual-encoding';

export { quantizeMetric } from '../visual-encoding';

export interface SurfaceBin {
  bin: number;
  color: string;
  cells: SurfaceCell[];
}

export interface SurfacePartitions {
  surface: SurfaceBin[];
  support: Record<'unknown' | 'prior_dominated', SurfaceCell[]>;
}

export function partitionSurfaceCells(
  cells: readonly SurfaceCell[],
  metric: Metric,
  domain: MetricDomain,
  palette?: PaletteId,
): SurfacePartitions {
  const support: SurfacePartitions['support'] = {
    prior_dominated: [],
    unknown: [],
  };
  const supported: SurfaceCell[] = [];

  for (const cell of cells) {
    if (cell.support === 'unknown' || cell.support === 'prior_dominated') {
      support[cell.support].push(cell);
      continue;
    }
    supported.push(cell);
  }

  return {
    support,
    surface: paletteBinsForCells(supported, metric, domain, palette),
  };
}

export function paletteBinsForCells(
  cells: readonly SurfaceCell[],
  metric: Metric,
  domain: MetricDomain,
  palette?: PaletteId,
): SurfaceBin[] {
  const bins = new Map<number, SurfaceCell[]>();
  for (const cell of cells) {
    const bin = quantizeMetric(cell[metric], domain);
    const binCells = bins.get(bin);
    if (binCells) binCells.push(cell);
    else bins.set(bin, [cell]);
  }

  return [...bins.entries()]
    .sort(([left], [right]) => left - right)
    .map(([bin, binCells]) => ({
      bin,
      cells: binCells,
      color: colorForCell(binCells[0], metric, domain, palette),
    }));
}

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
