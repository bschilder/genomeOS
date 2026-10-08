/** Deterministic atlas color and height encodings for Atlas design §11.
 *
 * The numeric colour path (`linearStops`, `colorBytesAtStops`) is shared by the
 * main thread and the Atlas data worker (fast-load spec 2026-10-07 §B.6.5), so
 * old and new geometry builders cannot drift. Everything here is Cesium-free.
 */

import type { Support, SurfaceCell } from './contracts';

export type Metric = 'post_mean' | 'post_sd';
export type MetricDomain = readonly [number, number];
export type PaletteId =
  'genome' | 'signal' | 'viridis' | 'cividis' | 'plasma' | 'rainbow' | 'golden';
/** One palette stop in linear light, each channel in [0, 1]. */
export type LinearRgb = readonly [number, number, number];

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

/** Position of `value` in `domain`, clamped to [0, 1]; 0 for an empty domain. */
export function normalizedValue(
  value: number,
  [lower, upper]: MetricDomain,
): number {
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

function linearFromHex(hex: string): LinearRgb {
  const [red, green, blue] = hexToRgb(hex);
  return [toLinear(red), toLinear(green), toLinear(blue)];
}

/** `#rrggbb` for 8-bit sRGB channels. */
export function hexFromBytes([red, green, blue]: readonly [
  number,
  number,
  number,
]): string {
  return `#${[red, green, blue]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('')}`;
}

const LINEAR_STOPS = {} as Record<PaletteId, readonly LinearRgb[]>;
for (const id of Object.keys(PALETTES) as PaletteId[])
  LINEAR_STOPS[id] = PALETTES[id].map(linearFromHex);

/** The palette's stops converted to linear light once (the only colour table). */
export function linearStops(palette: PaletteId): readonly LinearRgb[] {
  return LINEAR_STOPS[palette];
}

/** sRGB bytes at `t`: clamp, piecewise-linear in linear light, round to 8 bits. */
export function colorBytesAtStops(
  stopsLinear: readonly LinearRgb[],
  t: number,
): [number, number, number] {
  if (stopsLinear.length < 2)
    throw new Error('a color scale needs at least two stops');
  const bounded = clamp(t);
  const scaled = bounded * (stopsLinear.length - 1);
  const lower = Math.min(Math.floor(scaled), stopsLinear.length - 2);
  const amount = scaled - lower;
  const first = stopsLinear[lower];
  const second = stopsLinear[lower + 1];
  return [
    toSrgb(first[0] + (second[0] - first[0]) * amount),
    toSrgb(first[1] + (second[1] - first[1]) * amount),
    toSrgb(first[2] + (second[2] - first[2]) * amount),
  ];
}

export function colorForCell(
  cell: SurfaceCell,
  metric: Metric,
  domain: MetricDomain,
  paletteId: PaletteId = defaultPalette(metric),
): string {
  return colorAtPosition(paletteId, normalizedValue(cell[metric], domain));
}

export function colorAtPosition(
  paletteId: PaletteId,
  position: number,
): string {
  return hexFromBytes(colorBytesAtStops(LINEAR_STOPS[paletteId], position));
}

/** Custom stop list; `colorBytesAtStops` rejects fewer than two stops. */
export function colorAtStops(
  palette: readonly string[],
  position: number,
): string {
  return hexFromBytes(colorBytesAtStops(palette.map(linearFromHex), position));
}

/** 32-bin palette quantisation used for hexagon colours and support bins. */
export function quantizeMetric(
  value: number,
  domain: MetricDomain,
  bins = 32,
): number {
  if (bins < 2 || !Number.isInteger(bins))
    throw new Error('bins must be an integer >= 2');
  return Math.min(bins - 1, Math.floor(normalizedValue(value, domain) * bins));
}

/** Render height in metres; masked support states never rise (§B.2). */
export function heightFor(
  support: Support,
  value: number,
  domain: MetricDomain,
  exaggeration: number,
): number {
  if (support !== 'observed' && support !== 'interpolated') return 0;
  return (
    normalizedValue(value, domain) *
    MAX_HEIGHT_METRES *
    Math.max(0, exaggeration)
  );
}

export function heightForCell(
  cell: SurfaceCell,
  domain: MetricDomain,
  exaggeration: number,
  metric: Metric = 'post_mean',
): number {
  return heightFor(cell.support, cell[metric], domain, exaggeration);
}
