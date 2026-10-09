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
