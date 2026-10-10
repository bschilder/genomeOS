/** Verbatim copy of the pre-fast-load hex colour arithmetic from
 * `src/atlas/visual-encoding.ts` (HEAD 5a10b15), kept as the colour oracle
 * for fast-load spec 2026-10-07 §B.8 (colour sweep). Do not edit.
 */

function clamp(value: number, lower = 0, upper = 1): number {
  return Math.min(upper, Math.max(lower, value));
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

export function legacyColorAtStops(
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
