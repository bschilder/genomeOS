import { readFileSync } from 'node:fs';
import path from 'node:path';
import { inflateSync } from 'node:zlib';

import { describe, expect, it } from 'vitest';

const brand = path.resolve(import.meta.dirname, '../public/brand');
const lockup = readFileSync(
  path.join(brand, 'genomeos-foundation-dark.svg'),
  'utf8',
);
const wordmark = readFileSync(
  path.join(brand, 'genomeos-wordmark-dark.svg'),
  'utf8',
);
const headerLockup = readFileSync(
  path.join(brand, 'genomeos-lockup-dark.svg'),
  'utf8',
);

const rootTag = (svg: string) => svg.match(/<svg\b[^>]*>/)![0];
const attribute = (tag: string, name: string) =>
  tag.match(new RegExp(`\\s${name}="([^"]*)"`))![1];
const paths = (svg: string) => svg.match(/<path\b[^>]*\/>/g) ?? [];

/** The artwork with the parts the crop may change (root box, title, desc) blanked. */
const artwork = (svg: string) =>
  svg
    .replace(
      /(<svg\b[^>]*?) width="[^"]*" height="[^"]*" viewBox="[^"]*"/,
      '$1',
    )
    .replace(/(<title id="logo-title">)[^<]*(<\/title>)/, '$1$2')
    .replace(/(<desc id="logo-description">)[^<]*(<\/desc>)/, '$1$2');

describe('genomeOS brand assets', () => {
  it('keeps the full lockup at the artwork size', () => {
    const root = rootTag(lockup);
    expect(attribute(root, 'viewBox')).toBe('140 255 1380 435');
    expect(attribute(root, 'width')).toBe('1380');
    expect(attribute(root, 'height')).toBe('435');
    expect(lockup).toContain(
      'aria-label="open science for the benefit of all"',
    );
  });

  it('crops the wordmark from the same paths, byte for byte', () => {
    expect(paths(lockup)).toHaveLength(5);
    expect(paths(wordmark)).toEqual(paths(lockup));
  });

  it('changes only the root box and the title and description text', () => {
    expect(artwork(wordmark)).toBe(artwork(lockup));
    expect(wordmark).toContain('<title id="logo-title">genomeOS</title>');
    expect(wordmark).toContain('<desc id="logo-description">genomeOS</desc>');
  });

  it('sizes the crops at one user unit per pixel, like the lockup', () => {
    for (const crop of [wordmark, headerLockup]) {
      const root = rootTag(crop);
      const [, , width, height] = attribute(root, 'viewBox')
        .split(' ')
        .map(Number);
      expect(attribute(root, 'width')).toBe(String(width));
      expect(attribute(root, 'height')).toBe(String(height));
    }
  });
});

/** The full artwork's #tagline group, which the header lockup leaves out. */
const taglineGroup =
  /\n {2}<g id="tagline"[^>]*>\n(?: {4}<path\b[^>]*\/>\n)+ {2}<\/g>/;

describe('genomeOS header lockup (genome + OS + FOUNDATION)', () => {
  it('crops to the wordmark and FOUNDATION line measured in Chromium', () => {
    // Union of getBBox() for #wordmark-genome, #wordmark-os and
    // #foundation-line (163.793,276.449 to 1503.649,564.211), padded 2% per
    // axis and rounded outward.
    const root = rootTag(headerLockup);
    expect(attribute(root, 'viewBox')).toBe('136 270 1395 300');
  });

  it('keeps the wordmark and FOUNDATION paths byte for byte, without the tagline', () => {
    expect(lockup).toMatch(taglineGroup);
    expect(headerLockup).not.toContain('id="tagline"');
    expect(paths(headerLockup)).toEqual(paths(lockup).slice(0, 4));
    expect(paths(lockup)[4]).toContain('M256.310,661.710');
  });

  it('changes only the root box, the title and description, and drops the tagline', () => {
    expect(artwork(headerLockup)).toBe(
      artwork(lockup).replace(taglineGroup, ''),
    );
    expect(headerLockup).toContain(
      '<title id="logo-title">genomeOS Foundation</title>',
    );
    expect(headerLockup).toContain(
      '<desc id="logo-description">genomeOS Foundation</desc>',
    );
  });
});

const site = path.resolve(import.meta.dirname, '../public');
const favicon = readFileSync(path.join(site, 'favicon.svg'), 'utf8');
const binary = (name: string) => readFileSync(path.join(site, name));

/** The lines from `start` through the next line that is exactly `end`, indentation included. */
const block = (svg: string, start: string, end: string) => {
  const from = svg.indexOf(start);
  expect(from, start).toBeGreaterThanOrEqual(0);
  // A missing end line would otherwise slice an empty string, which every
  // comparison below would accept.
  const close = svg.indexOf(`\n${end}\n`, from);
  expect(close, end).toBeGreaterThan(from);
  return svg.slice(from, close + end.length + 1);
};

/** Width and height from a PNG's IHDR chunk, which always follows the signature. */
const pngSize = (png: Buffer) => {
  expect(png.subarray(0, 8)).toEqual(
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  );
  expect(png.toString('latin1', 12, 16)).toBe('IHDR');
  return [png.readUInt32BE(16), png.readUInt32BE(20)];
};

/** The Paeth predictor of PNG filter type 4. */
const paeth = (left: number, up: number, upLeft: number) => {
  const estimate = left + up - upLeft;
  const [toLeft, toUp, toUpLeft] = [left, up, upLeft].map((value) =>
    Math.abs(estimate - value),
  );
  if (toLeft <= toUp && toLeft <= toUpLeft) return left;
  return toUp <= toUpLeft ? up : upLeft;
};

/**
 * RGBA pixels of an 8-bit, non-interlaced RGBA PNG, the kind Chromium writes
 * for a screenshot with a transparent background. node:zlib inflates; the
 * five scanline filters are undone here, so no image package is needed.
 */
const decodePng = (png: Buffer) => {
  const [width, height] = pngSize(png);
  // Bit depth 8, colour type 6 (RGBA), no interlacing.
  expect([png[24], png[25], png[28]]).toEqual([8, 6, 0]);
  const data: Buffer[] = [];
  for (let offset = 8; offset < png.length;) {
    const length = png.readUInt32BE(offset);
    if (png.toString('latin1', offset + 4, offset + 8) === 'IDAT')
      data.push(png.subarray(offset + 8, offset + 8 + length));
    offset += 12 + length; // length, type, data, CRC
  }
  const scanlines = inflateSync(Buffer.concat(data));
  const stride = 4 * width;
  expect(scanlines.length).toBe((stride + 1) * height);
  const pixels = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = scanlines[y * (stride + 1)];
    expect(filter, `filter of row ${y}`).toBeLessThan(5);
    for (let i = 0; i < stride; i++) {
      const left = i >= 4 ? pixels[y * stride + i - 4] : 0;
      const up = y > 0 ? pixels[(y - 1) * stride + i] : 0;
      const upLeft = i >= 4 && y > 0 ? pixels[(y - 1) * stride + i - 4] : 0;
      const predicted = [
        0,
        left,
        up,
        (left + up) >> 1,
        paeth(left, up, upLeft),
      ][filter];
      pixels[y * stride + i] =
        (scanlines[y * (stride + 1) + 1 + i] + predicted) & 0xff;
    }
  }
  return {
    width,
    height,
    pixel: (x: number, y: number) => [
      ...pixels.subarray(4 * (y * width + x), 4 * (y * width + x) + 4),
    ],
  };
};

describe('genomeOS favicon', () => {
  it('keeps only the gradient and the OS paths, byte for byte', () => {
    for (const [start, end] of [
      ['  <defs>', '  </defs>'],
      ['  <g id="wordmark-os"', '  </g>'],
    ]) {
      const kept = block(favicon, start, end);
      expect(kept).toBe(block(lockup, start, end));
      expect(favicon).toContain(kept);
    }
    expect(paths(favicon)).toEqual(
      paths(block(lockup, '  <g id="wordmark-os"', '  </g>')),
    );
    expect(paths(favicon)).toHaveLength(2);
    for (const dropped of ['wordmark-genome', 'foundation-line', 'tagline']) {
      expect(favicon).not.toContain(dropped);
    }
  });

  it('adds only a clip circle around the O and a dark backing circle', () => {
    // Everything outside the logo's own defs and OS group: the root and its
    // title, the clip that cuts away the S, the backing, and the <g> that
    // applies the clip (the OS group itself must stay byte for byte).
    const added = [
      block(favicon, '  <defs>', '  </defs>'),
      block(favicon, '  <g id="wordmark-os"', '  </g>'),
    ].reduce((svg, kept) => svg.replace(kept, ''), favicon);
    expect(added.match(/<[a-zA-Z][^\s/>]*/g)).toEqual([
      '<svg',
      '<title',
      '<clipPath',
      '<circle',
      '<circle',
      '<g',
    ]);

    const clipPath = added.match(
      /<clipPath id="([^"]+)">\s*(<circle\b[^>]*\/>)\s*<\/clipPath>/,
    );
    expect(clipPath, 'a clipPath holding one circle').not.toBeNull();
    const [, clipId, clip] = clipPath!;
    const backing = added.match(/<circle id="favicon-backing"[^>]*\/>/)?.[0];
    expect(backing, 'the backing circle').toBeDefined();
    // The header ground: the cyan end of the gradient is about 1.1:1 on a
    // light tab strip, while on #020712 every stop clears 3:1.
    expect(attribute(backing!, 'fill')).toBe('#020712');

    // The O's group is wrapped in the clip, drawn after (over) the backing.
    const wrapper = `  <g clip-path="url(#${clipId})">\n  <g id="wordmark-os"`;
    expect(favicon).toContain(wrapper);
    expect(favicon.indexOf(backing!)).toBeLessThan(favicon.indexOf(wrapper));

    // Concentric, with the backing 1.12 times the O's radius and the clip
    // 1.5 logo units past it, and the viewBox the backing's bounding box.
    const circle = (tag: string) =>
      ['cx', 'cy', 'r'].map((name) => Number(attribute(tag, name)));
    const [cx, cy, backingR] = circle(backing!);
    const [clipX, clipY, clipR] = circle(clip);
    expect([clipX, clipY]).toEqual([cx, cy]);
    expect(clipR).toBeCloseTo(backingR / 1.12 + 1.5, 2);
    const [x, y, side] = attribute(rootTag(favicon), 'viewBox')
      .split(' ')
      .map(Number);
    expect(x + side / 2).toBeCloseTo(cx, 2);
    expect(y + side / 2).toBeCloseTo(cy, 2);
    expect(side / 2).toBeCloseTo(backingR, 2);
    expect(favicon).not.toContain('<rect');
  });

  it('has a square viewBox', () => {
    const [, , width, height] = attribute(rootTag(favicon), 'viewBox')
      .split(' ')
      .map(Number);
    expect(width).toBeGreaterThan(0);
    expect(width).toBe(height);
  });

  it('draws the 32 px PNG as an opaque disc with transparent corners', () => {
    const icon = decodePng(binary('favicon-32.png'));
    expect(icon.width).toBe(32);
    /** Pixels whose centres lie `from` to `to` px from the image centre. */
    const ring = (from: number, to: number) => {
      const found: number[][] = [];
      for (let y = 0; y < 32; y++) {
        for (let x = 0; x < 32; x++) {
          const distance = Math.hypot(x + 0.5 - 16, y + 0.5 - 16);
          if (distance >= from && distance < to) found.push(icon.pixel(x, y));
        }
      }
      return found;
    };
    // The backing's rim is 16 px out; a pixel 0.75 px clear of it either
    // way is wholly inside or wholly outside it.
    expect(ring(0, 15.25).every(([, , , alpha]) => alpha === 255)).toBe(true);
    for (const [x, y] of [
      [0, 0],
      [31, 0],
      [0, 31],
      [31, 31],
    ] as const) {
      expect(icon.pixel(x, y)[3], `corner ${x},${y}`).toBe(0);
    }
    expect(ring(16.75, 99).every(([, , , alpha]) => alpha === 0)).toBe(true);
    // Between the clipped O (14.5 px out) and the rim, the backing shows.
    const edge = ring(14.75, 15.25);
    const ground = edge.filter(
      ([red, green, blue, alpha]) =>
        alpha === 255 &&
        Math.abs(red - 2) <= 4 &&
        Math.abs(green - 7) <= 4 &&
        Math.abs(blue - 18) <= 4,
    );
    expect(edge.length).toBeGreaterThan(30);
    expect(ground.length / edge.length).toBeGreaterThan(0.85);
  });

  it.each([
    ['favicon-16.png', 16],
    ['favicon-32.png', 32],
    ['favicon-48.png', 48],
    ['apple-touch-icon.png', 180],
  ])('renders %s at %i px square', (name, size) => {
    expect(pngSize(binary(name))).toEqual([size, size]);
  });

  it('packs the 16, 32 and 48 px PNGs into favicon.ico', () => {
    const ico = binary('favicon.ico');
    expect([ico.readUInt16LE(0), ico.readUInt16LE(2)]).toEqual([0, 1]);
    const count = ico.readUInt16LE(4);
    const images = Array.from({ length: count }, (_, index) => {
      const entry = 6 + 16 * index;
      const length = ico.readUInt32LE(entry + 8);
      const offset = ico.readUInt32LE(entry + 12);
      return {
        size: [ico.readUInt8(entry), ico.readUInt8(entry + 1)],
        png: ico.subarray(offset, offset + length),
      };
    });
    expect(images.map(({ size }) => size)).toEqual([
      [16, 16],
      [32, 32],
      [48, 48],
    ]);
    for (const { size, png } of images) {
      expect(png.equals(binary(`favicon-${size[0]}.png`))).toBe(true);
    }
  });
});
