/** Surface batching and support materials for Atlas design §11. */

import { Cartesian2, Color, Material } from 'cesium';

import type { Support, SurfaceCell } from '../contracts';
import {
  colorForCell,
  type Metric,
  type MetricDomain,
  type PaletteId,
} from '../visual-encoding';

export interface SurfaceBin {
  bin: number;
  color: string;
  cells: SurfaceCell[];
}

export interface SurfacePartitions {
  surface: SurfaceBin[];
  support: Record<'unknown' | 'prior_dominated', SurfaceCell[]>;
}

export function quantizeMetric(
  value: number,
  [lower, upper]: MetricDomain,
  bins = 32,
): number {
  if (bins < 2 || !Number.isInteger(bins))
    throw new Error('bins must be an integer >= 2');
  if (lower === upper) return 0;
  const normalized = Math.min(
    1,
    Math.max(0, (value - lower) / (upper - lower)),
  );
  return Math.min(bins - 1, Math.floor(normalized * bins));
}

export function partitionSurfaceCells(
  cells: readonly SurfaceCell[],
  metric: Metric,
  domain: MetricDomain,
  palette?: PaletteId,
): SurfacePartitions {
  const bins = new Map<number, SurfaceCell[]>();
  const support: SurfacePartitions['support'] = {
    prior_dominated: [],
    unknown: [],
  };

  for (const cell of cells) {
    if (cell.support === 'unknown' || cell.support === 'prior_dominated') {
      support[cell.support].push(cell);
      continue;
    }
    const bin = quantizeMetric(cell[metric], domain);
    bins.set(bin, [...(bins.get(bin) ?? []), cell]);
  }

  return {
    support,
    surface: [...bins.entries()]
      .sort(([left], [right]) => left - right)
      .map(([bin, binCells]) => ({
        bin,
        cells: binCells,
        color: colorForCell(binCells[0], metric, domain, palette),
      })),
  };
}

export function materialForSupport(
  support: Extract<Support, 'unknown' | 'prior_dominated'>,
): Material {
  if (support === 'unknown') {
    return Material.fromType('Grid', {
      cellAlpha: 0.24,
      color: Color.fromCssColorString('#a8b5c9').withAlpha(0.72),
      lineCount: new Cartesian2(5, 5),
      lineThickness: new Cartesian2(1.65, 1.65),
    });
  }
  return Material.fromType('Dot', {
    darkColor: Color.fromCssColorString('#24144b').withAlpha(0.42),
    lightColor: Color.fromCssColorString('#ad8bff').withAlpha(0.74),
    repeat: new Cartesian2(10, 10),
  });
}
