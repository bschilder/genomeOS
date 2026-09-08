/** Deterministic atlas color and height encodings for Atlas design §11. */

import type { SurfaceCell } from './contracts';

export type Metric = 'post_mean' | 'post_sd';
export type MetricDomain = readonly [number, number];
export type PaletteId =
  'genome' | 'signal' | 'viridis' | 'cividis' | 'plasma' | 'rainbow' | 'golden';

const MAX_HEIGHT_METRES = 180_000;
const PALETTES: Record<PaletteId, readonly string[]> = {
  cividis: ['#00204c', '#7d7c78', '#fee838'],
  genome: ['#10213e', '#27a9d0', '#72e7c1'],
  golden: ['#241133', '#7a3f18', '#d49425', '#f4c86a', '#fff3bd'],
  plasma: ['#0d0887', '#cc4778', '#f0f921'],
  rainbow: ['#6e40aa', '#417de0', '#1ac7c2', '#7bd34d', '#f2cf44', '#ff5e63'],
  signal: ['#24144b', '#ad8bff', '#f4c86a'],
  viridis: ['#440154', '#21918c', '#fde725'],
};

export function defaultPalette(metric: Metric): PaletteId {
  return metric === 'post_mean' ? 'rainbow' : 'plasma';
}

export function paletteStops(palette: PaletteId): readonly string[] {
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
  return colorAtStops(PALETTES[paletteId], position);
}

export function colorAtStops(
  palette: readonly string[],
  position: number,
): string {
  if (palette.length < 2)
    throw new Error('a color scale needs at least two stops');
  const bounded = clamp(position);
  const scaled = bounded * (palette.length - 1);
  const lower = Math.min(Math.floor(scaled), palette.length - 2);
  return interpolateColor(palette[lower], palette[lower + 1], scaled - lower);
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
