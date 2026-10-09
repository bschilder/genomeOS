import { readFileSync } from 'node:fs';
import path from 'node:path';

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

  it('sizes the crop at one user unit per pixel, like the lockup', () => {
    const root = rootTag(wordmark);
    const [, , width, height] = attribute(root, 'viewBox')
      .split(' ')
      .map(Number);
    expect(attribute(root, 'width')).toBe(String(width));
    expect(attribute(root, 'height')).toBe(String(height));
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

  it('has a square viewBox', () => {
    const [, , width, height] = attribute(rootTag(favicon), 'viewBox')
      .split(' ')
      .map(Number);
    expect(width).toBeGreaterThan(0);
    expect(width).toBe(height);
  });

  it('backs OS with one dark tile that fills the viewBox', () => {
    // The cyan end of the gradient is about 1.1:1 on a light tab strip; on
    // the header ground #020712 every stop clears 3:1.
    const tiles = favicon.match(/<rect\b[^>]*\/>/g) ?? [];
    expect(tiles).toHaveLength(1);
    const tile = tiles[0]!;
    expect(attribute(tile, 'id')).toBe('favicon-tile');
    expect(attribute(tile, 'fill')).toBe('#020712');
    const [x, y, side] = attribute(rootTag(favicon), 'viewBox')
      .split(' ')
      .map(Number);
    expect(
      ['x', 'y', 'width', 'height'].map((name) =>
        Number(attribute(tile, name)),
      ),
    ).toEqual([x, y, side, side]);
    expect(Number(attribute(tile, 'rx'))).toBeCloseTo(side * 0.2, 3);
    // Drawn first, so it sits behind the OS group.
    expect(favicon.indexOf(tile)).toBeLessThan(
      favicon.indexOf('<g id="wordmark-os"'),
    );
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
