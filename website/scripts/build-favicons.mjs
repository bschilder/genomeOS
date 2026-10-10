/**
 * Build the site favicons from the globe "O" of the genomeOS logo.
 *
 * favicon.svg keeps the logo's gradient <defs> and its #wordmark-os group (the
 * OS outline and the continent silhouettes) byte for byte, and drops "genome",
 * the FOUNDATION line and the tagline. Coordinates stay in the logo's user
 * space, so the userSpaceOnUse gradient lands exactly where it does in the logo.
 *
 * Only the O is shown. It is approximately the left square of the OS group:
 * its side is taken as the group's height, measured with getBBox() in
 * Chromium. That height comes from the S, which reaches about 3.8 units lower
 * than the O, so the circle runs about that far below the O's own bottom edge.
 * A circular clipPath, 1.5 units wider than that circle so the O's anti-aliased
 * rim survives, wraps the group and cuts away the S together with the stub
 * where the O joins it.
 *
 * The O sits on a circle of the header ground #020712, the dark ground the
 * logo is drawn for, 1.12 times its radius. Without it the cyan end of the
 * gradient (#12ffff) all but vanishes on a light tab strip (about 1.1:1
 * against Chrome's #f1f3f4); on the backing every stop of the gradient clears
 * 3:1. Chrome and Firefox draw the SVG itself at 16 px, so the backing has to
 * live in the SVG, not only in the PNGs. The square viewBox is the backing
 * circle's bounding box.
 *
 * The raster fallbacks are rendered from favicon.svg by the same Chromium
 * (Playwright, already a dev dependency), so no image tooling is needed:
 *
 *   favicon-16.png, favicon-32.png, favicon-48.png   the round backing,
 *                          transparent outside it
 *   apple-touch-icon.png   180 x 180 on a solid square of #020712, because iOS
 *                          fills transparency with black and masks the corners
 *                          itself; the O spans 70% of it, with no backing circle
 *   favicon.ico            the 16, 32 and 48 px PNGs in one ICO container
 *
 * Run from website/ with `npm run build:favicons`, then commit public/.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import { chromium } from '@playwright/test';

const publicDir = path.resolve(import.meta.dirname, '../public');
const logo = readFileSync(
  path.join(publicDir, 'brand/genomeos-foundation-dark.svg'),
  'utf8',
);

/** Transparent tab icons; 48 px is the smallest size Google Search accepts. */
const ICON_SIZES = [16, 32, 48];
const APPLE_SIZE = 180;
/** Share of the apple-touch-icon width the O spans. */
const APPLE_FILL = 0.7;
/** The site header background (global.css `.site-header`). */
const GROUND = '#020712';
/** How far the clip circle reaches past the O's radius, in logo units. */
const CLIP_BLEED = 1.5;
/** Radius of the backing circle, as a multiple of the O's radius. */
const BACKING_SCALE = 1.12;

function extract(pattern, name) {
  const match = logo.match(pattern);
  if (!match) throw new Error(`${name} not found in the logo`);
  return match[0];
}

const defs = extract(/^ {2}<defs>\n[\s\S]*?^ {2}<\/defs>$/m, 'gradient defs');
const os = extract(/^ {2}<g id="wordmark-os"[\s\S]*?^ {2}<\/g>$/m, 'OS group');

const round = (value) => Number(value.toFixed(3));

/**
 * The O, approximately: the left square of the OS group, as a circle in logo
 * units (the group's height comes from the S, about 3.8 units below the O).
 */
function globeOf(box) {
  const r = box.height / 2;
  return { cx: box.x + r, cy: box.y + r, r };
}

/** A square viewBox of side `side` centred on (cx, cy). */
const frameAround = ({ cx, cy }, side) =>
  [round(cx - side / 2), round(cy - side / 2), round(side), round(side)].join(
    ' ',
  );

const faviconSvg = ({ cx, cy, r }, viewBox) => {
  const centre = `cx="${round(cx)}" cy="${round(cy)}"`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" role="img" aria-labelledby="favicon-title">
  <title id="favicon-title">genomeOS</title>
${defs}
  <clipPath id="favicon-globe-clip">
    <circle ${centre} r="${round(r + CLIP_BLEED)}"/>
  </clipPath>
  <circle id="favicon-backing" ${centre} r="${round(r * BACKING_SCALE)}" fill="${GROUND}"/>
  <g clip-path="url(#favicon-globe-clip)">
${os}
  </g>
</svg>
`;
};

/** PNG-in-ICO container (Windows Vista and every current browser read it). */
function icoFrom(images) {
  const directory = Buffer.alloc(6 + 16 * images.length);
  directory.writeUInt16LE(0, 0); // reserved
  directory.writeUInt16LE(1, 2); // 1 = icon
  directory.writeUInt16LE(images.length, 4);
  let offset = directory.length;
  images.forEach(({ size, png }, index) => {
    const entry = 6 + 16 * index;
    directory.writeUInt8(size % 256, entry); // width, 0 means 256
    directory.writeUInt8(size % 256, entry + 1); // height
    directory.writeUInt8(0, entry + 2); // no palette
    directory.writeUInt8(0, entry + 3); // reserved
    directory.writeUInt16LE(1, entry + 4); // colour planes
    directory.writeUInt16LE(32, entry + 6); // bits per pixel
    directory.writeUInt32LE(png.length, entry + 8);
    directory.writeUInt32LE(offset, entry + 12);
    offset += png.length;
  });
  return Buffer.concat([directory, ...images.map(({ png }) => png)]);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  const show = (svg) =>
    page.setContent(
      `<style>body{margin:0}svg{display:block}</style>${svg.replace(/^<\?xml[^>]*>\n/, '')}`,
    );

  await show(logo);
  const box = await page.evaluate(() => {
    const { x, y, width, height } = document
      .querySelector('#wordmark-os')
      .getBBox();
    return { x, y, width, height };
  });
  const globe = globeOf(box);
  const viewBox = frameAround(globe, 2 * globe.r * BACKING_SCALE);
  const svg = faviconSvg(globe, viewBox);
  writeFileSync(path.join(publicDir, 'favicon.svg'), svg);

  const render = async (size, { frame = viewBox, ground } = {}) => {
    await show(svg);
    const icon = page.locator('svg');
    await icon.evaluate(
      (element, { size, frame, ground }) => {
        element.setAttribute('width', String(size));
        element.setAttribute('height', String(size));
        element.setAttribute('viewBox', frame);
        if (!ground) return;
        // An opaque square replaces the backing circle; iOS rounds the corners.
        element.querySelector('#favicon-backing').remove();
        element.style.background = ground;
      },
      { size, frame, ground },
    );
    return icon.screenshot({ omitBackground: !ground });
  };

  const icons = [];
  for (const size of ICON_SIZES) {
    const png = await render(size);
    writeFileSync(path.join(publicDir, `favicon-${size}.png`), png);
    icons.push({ size, png });
  }
  writeFileSync(path.join(publicDir, 'favicon.ico'), icoFrom(icons));
  writeFileSync(
    path.join(publicDir, 'apple-touch-icon.png'),
    await render(APPLE_SIZE, {
      frame: frameAround(globe, (2 * globe.r) / APPLE_FILL),
      ground: GROUND,
    }),
  );

  console.log(
    `OS getBBox ${[box.x, box.y, box.width, box.height].join(' ')}; ` +
      `O centre ${round(globe.cx)} ${round(globe.cy)} radius ${round(globe.r)}; ` +
      `favicon viewBox ${viewBox}`,
  );
} finally {
  await browser.close();
}
