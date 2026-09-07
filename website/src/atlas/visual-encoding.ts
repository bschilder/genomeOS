/** Deterministic atlas color and height encodings for Atlas design §11. */

import type { SurfaceCell } from './contracts';

export type Metric = 'post_mean' | 'post_sd';
export type MetricDomain = readonly [number, number];
export type PaletteId = 'genome' | 'signal' | 'viridis' | 'cividis' | 'plasma';

const MAX_HEIGHT_METRES = 180_000;
const PALETTES: Record<PaletteId, readonly [string, string, string]> = {
  cividis: ['#00204c', '#7d7c78', '#fee838'],
  genome: ['#10213e', '#27a9d0', '#72e7c1'],
  plasma: ['#0d0887', '#cc4778', '#f0f921'],
  signal: ['#24144b', '#ad8bff', '#f4c86a'],
  viridis: ['#440154', '#21918c', '#fde725'],
};

export function defaultPalette(metric: Metric): PaletteId {
  return metric === 'post_mean' ? 'genome' : 'signal';
}

export function paletteStops(
  palette: PaletteId,
): readonly [string, string, string] {
  return PALETTES[palette];
}

function clamp(value: number, lower = 0, upper = 1): number {
  return Math.min(upper, Math.max(lower, value));
}

function normalized(value: number, [lower, upper]: MetricDomain): number {
  if (lower === upper) return 0;
  return clamp((value - lower) / (upper - lower));
}

function hexToRgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((offset) =>
    Number.parseInt(hex.slice(offset, offset + 2), 16),
  ) as [number, number, number];
}

function toLinear(channel: number): number {
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function toSrgb(channel: number): number {
  const value =
    channel <= 0.0031308
      ? channel * 12.92
      : 1.055 * channel ** (1 / 2.4) - 0.055;
  return Math.round(clamp(value) * 255);
}

function interpolateColor(start: string, end: string, amount: number): string {
  const first = hexToRgb(start).map(toLinear);
  const second = hexToRgb(end).map(toLinear);
  const channels = first.map((value, index) =>
    toSrgb(value + (second[index] - value) * amount),
  );
  return `#${channels.map((value) => value.toString(16).padStart(2, '0')).join('')}`;
}

export function colorForCell(
  cell: SurfaceCell,
  metric: Metric,
  domain: MetricDomain,
  paletteId: PaletteId = defaultPalette(metric),
): string {
  const position = normalized(cell[metric], domain);
  return colorAtPosition(paletteId, position);
}

export function colorAtPosition(
  paletteId: PaletteId,
  position: number,
): string {
  const palette = PALETTES[paletteId];
  const bounded = clamp(position);
  if (bounded <= 0.5)
    return interpolateColor(palette[0], palette[1], bounded * 2);
  return interpolateColor(palette[1], palette[2], (bounded - 0.5) * 2);
}

export function heightForCell(
  cell: SurfaceCell,
  domain: MetricDomain,
  exaggeration: number,
  metric: Metric = 'post_mean',
): number {
  if (cell.support !== 'observed' && cell.support !== 'interpolated') return 0;
  return (
    normalized(cell[metric], domain) *
    MAX_HEIGHT_METRES *
    Math.max(0, exaggeration)
  );
}
