/**
 * Build the site favicons from the globe "OS" of the genomeOS logo.
 *
 * favicon.svg keeps the logo's gradient <defs> and its #wordmark-os group (the
 * OS outline and the continent silhouettes) byte for byte, and drops "genome",
 * the FOUNDATION line and the tagline. Its square viewBox is centred on the
 * group's getBBox(), measured in Chromium, with 6% of the side left clear on
 * each side of the wider axis. OS is wider than tall, so it is letterboxed
 * vertically rather than stretched. Coordinates stay in the logo's user space,
 * so the userSpaceOnUse gradient lands exactly where it does in the logo.
 *
 * OS sits on a rounded tile of the header ground #020712, the dark ground the
 * logo is drawn for. Without it the cyan end of the gradient (#12ffff) all but
 * vanishes on a light tab strip (about 1.1:1 against Chrome's #f1f3f4); on the
 * tile every stop of the gradient clears 3:1. Chrome and Firefox draw the SVG
 * itself at 16 px, so the backing has to live in the SVG, not only in the PNGs.
 *
 * The raster fallbacks are rendered from favicon.svg by the same Chromium
 * (Playwright, already a dev dependency), so no image tooling is needed:
 *
 *   favicon-16.png, favicon-32.png, favicon-48.png   the tile, transparent corners
 *   apple-touch-icon.png   180 x 180 on the site header's #020712, because iOS
 *                          fills transparency with black; OS spans 70% of it
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

/** Clear space on each side of the wider axis, as a fraction of the side. */
const PADDING = 0.06;
/** Transparent tab icons; 48 px is the smallest size Google Search accepts. */
const ICON_SIZES = [16, 32, 48];
const APPLE_SIZE = 180;
/** Share of the apple-touch-icon width the OS spans. */
const APPLE_FILL = 0.7;
/** The site header background (global.css `.site-header`). */
const GROUND = '#020712';
/** Corner radius of the favicon tile, as a fraction of its side. */
const TILE_RADIUS = 0.2;

function extract(pattern, name) {
  const match = logo.match(pattern);
  if (!match) throw new Error(`${name} not found in the logo`);
  return match[0];
}

const defs = extract(/^ {2}<defs>\n[\s\S]*?^ {2}<\/defs>$/m, 'gradient defs');
const os = extract(/^ {2}<g id="wordmark-os"[\s\S]*?^ {2}<\/g>$/m, 'OS group');

const round = (value) => Number(value.toFixed(3));

/** A square box [x, y, side, side] centred on `box`, in which the wider axis spans `fill`. */
function squareFrame(box, fill) {
  const side = Math.ceil(Math.max(box.width, box.height) / fill);
  return [
    round(box.x + box.width / 2 - side / 2),
    round(box.y + box.height / 2 - side / 2),
    side,
    side,
  ];
}

const faviconSvg = ([x, y, side]) => `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="${[x, y, side, side].join(' ')}" role="img" aria-labelledby="favicon-title">
  <title id="favicon-title">genomeOS</title>
${defs}
  <rect id="favicon-tile" x="${x}" y="${y}" width="${side}" height="${side}" rx="${round(side * TILE_RADIUS)}" fill="${GROUND}"/>
${os}
</svg>
`;

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
  const iconFrame = squareFrame(box, 1 - 2 * PADDING);
  const viewBox = iconFrame.join(' ');
  const svg = faviconSvg(iconFrame);
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
        // An opaque ground replaces the tile; iOS rounds the corners itself.
        element.querySelector('#favicon-tile').remove();
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
      frame: squareFrame(box, APPLE_FILL).join(' '),
      ground: GROUND,
    }),
  );

  console.log(
    `OS getBBox ${[box.x, box.y, box.width, box.height].join(' ')}; favicon viewBox ${viewBox}`,
  );
} finally {
  await browser.close();
}
