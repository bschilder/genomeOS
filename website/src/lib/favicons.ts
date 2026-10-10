/**
 * The favicon set, built into public/ by scripts/build-favicons.mjs from the
 * globe "O" of the genomeOS logo, drawn on a dark circle. SiteLayout
 * pages and the standalone /app/polygon/ page link every entry; the Starlight
 * docs link the SVG through Starlight's `favicon` option and the raster
 * entries through its `head` option, so every page declares the same icons.
 * favicon.ico (16, 32 and 48 px) sits unlinked at the site root for clients
 * that request /favicon.ico directly.
 */
import { sitePath } from './paths';

/** The primary icon, a root-relative path as Starlight's `favicon` expects. */
export const FAVICON_SVG = '/favicon.svg';

export interface IconLink {
  rel: 'icon' | 'apple-touch-icon';
  href: string;
  sizes?: string;
  type?: string;
}

/** Raster fallbacks for browsers without SVG favicons, and the iOS home-screen icon. */
export function rasterIconLinks(
  base: string = import.meta.env.BASE_URL,
): IconLink[] {
  return [
    {
      rel: 'icon',
      href: sitePath('/favicon-32.png', base),
      sizes: '32x32',
      type: 'image/png',
    },
    {
      rel: 'icon',
      href: sitePath('/favicon-16.png', base),
      sizes: '16x16',
      type: 'image/png',
    },
    { rel: 'apple-touch-icon', href: sitePath('/apple-touch-icon.png', base) },
  ];
}
