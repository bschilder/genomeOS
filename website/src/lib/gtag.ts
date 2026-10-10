/**
 * The page's `gtag` command queue (#422). The analytics head bootstrap (`ga.mjs`) defines it
 * before any module runs, on pages of a build that loads analytics; everywhere else it is absent.
 */

export type Gtag = (...args: unknown[]) => void;

declare global {
  interface Window {
    gtag?: Gtag;
  }
}

/** This page's `gtag`, or undefined when the page loads no analytics. */
export function pageGtag(): Gtag | undefined {
  if (typeof window === 'undefined') return undefined;
  const gtag = window.gtag;
  return typeof gtag === 'function' ? gtag : undefined;
}
