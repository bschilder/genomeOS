/**
 * The `/app/` head script for fast-load design §B.6.1: it reads the inline catalog and the URL
 * entity and preloads that artifact's grid, render and observations with exactly the URLs the
 * provider later fetches (same resolution rule as `resolveDataUrl`, same CORS mode).
 */

import { INLINE_CATALOG_ID } from './inline-catalog';

const SOURCE = `(() => {
  try {
    const element = document.getElementById(${JSON.stringify(INLINE_CATALOG_ID)});
    const base = element && element.getAttribute('data-artifact-data-base');
    if (!element || !base) return;
    const catalog = JSON.parse(element.textContent || '');
    const requested = new URLSearchParams(location.search).get('entity');
    const ref = requested === null
      ? catalog.artifacts[0]
      : catalog.artifacts.find((artifact) => artifact.id === requested);
    if (!ref) return;
    const grid = catalog.grids[ref.web.grid_sha256];
    const root = new URL(base, document.baseURI);
    for (const key of [grid && grid.url, ref.web.render.url, ref.observations_available ? ref.observations_url : null]) {
      if (!key) continue;
      const link = document.createElement('link');
      link.rel = 'preload';
      link.as = 'fetch';
      link.crossOrigin = 'anonymous';
      link.href = new URL(key, root).href;
      document.head.appendChild(link);
    }
  } catch (error) {
    // Preloading is an optimisation; the explorer reports catalog problems itself.
  }
})();`;

export function preloadScriptSource(): string {
  return SOURCE;
}
