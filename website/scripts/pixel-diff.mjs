/** Pixel-difference fractions for the fast-load parity figures (fast-load design §B.1 "Visual parity"). */

/**
 * Count pixels whose largest RGBA channel difference is > 0, > tolerance and > 16.
 * @param {Uint8Array | Uint8ClampedArray} before
 * @param {Uint8Array | Uint8ClampedArray} after
 * @param {number} tolerance
 */
export function countPixelDifferences(before, after, tolerance) {
  if (before.length !== after.length || before.length % 4 !== 0)
    throw new Error(
      `RGBA buffers differ in size: ${before.length} vs ${after.length}`,
    );
  let any = 0;
  let overTolerance = 0;
  let over16 = 0;
  for (let index = 0; index < before.length; index += 4) {
    let delta = 0;
    for (let channel = 0; channel < 4; channel += 1)
      delta = Math.max(
        delta,
        Math.abs(before[index + channel] - after[index + channel]),
      );
    if (delta > 0) any += 1;
    if (delta > tolerance) overTolerance += 1;
    if (delta > 16) over16 += 1;
  }
  const pixels = before.length / 4;
  return {
    pixels,
    fractionAny: any / pixels,
    fractionOverTolerance: overTolerance / pixels,
    fractionOver16: over16 / pixels,
  };
}

/**
 * Gate every pair of every view: a pair passes when at most `maxFraction` of its pixels differ by
 * more than the channel tolerance, and the run fails when any pair of any view does not.
 * @template {{ fractionOverTolerance: number }} Pair
 * @param {Record<string, Pair[]>} views
 * @param {number} maxFraction
 * @returns {{ failed: boolean, views: Record<string, (Pair & { pass: boolean })[]> }}
 */
export function gateViews(views, maxFraction) {
  /** @type {Record<string, (Pair & { pass: boolean })[]>} */
  const gated = {};
  for (const [view, pairs] of Object.entries(views))
    gated[view] = pairs.map((pair) => ({
      ...pair,
      pass: pair.fractionOverTolerance <= maxFraction,
    }));
  return {
    failed: Object.values(gated).some((pairs) =>
      pairs.some((pair) => !pair.pass),
    ),
    views: gated,
  };
}

/**
 * Decode a PNG to raw RGBA in the browser (no PNG dependency in Node).
 * @param {import('playwright').Page} page
 * @param {Buffer} png
 */
export async function decodePng(page, png) {
  const decoded = await page.evaluate(async (pngBase64) => {
    const blob = await (
      await fetch(`data:image/png;base64,${pngBase64}`)
    ).blob();
    const bitmap = await createImageBitmap(blob, {
      colorSpaceConversion: 'none',
      premultiplyAlpha: 'none',
    });
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('No 2D context for PNG decoding.');
    context.drawImage(bitmap, 0, 0);
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    const dataUrl = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsDataURL(new Blob([data]));
    });
    return {
      width: bitmap.width,
      height: bitmap.height,
      base64: dataUrl.slice(dataUrl.indexOf(',') + 1),
    };
  }, png.toString('base64'));
  return {
    width: decoded.width,
    height: decoded.height,
    data: new Uint8Array(Buffer.from(decoded.base64, 'base64')),
  };
}
