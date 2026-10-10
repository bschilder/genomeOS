/**
 * The `/app/` head script for fast-load design §B.6.1: it reads the inline catalog and the URL
 * entity and preloads that artifact's grid, render and observations with exactly the URLs the
 * provider later fetches (same resolution rule as `resolveDataUrl`, same CORS mode, same priority).
 *
 * Network priority (§B.1, ruling R84-slow4g): the observations are what the first frame shows, so
 * they preload at high priority and the grid and render tiers at low priority. On a slow
 * connection (`navigator.connection` reports Save-Data or an effective type of 3g or slower; the
 * DevTools Slow 4G preset reads as 3g) the render tier, the one large surface object, is not
 * preloaded at all: the script records `data-surface-downloads="after-scene"` on the catalog
 * element, and the provider starts it once the scene chunk has arrived, so it does not share the
 * link with Cesium and the observations. The grid (about 11 kB) still preloads, so the worker's
 * topology is ready when the render tier arrives. A browser without `navigator.connection`
 * preloads all three.
 */

import {
  INLINE_CATALOG_ID,
  OBSERVATIONS_PRIORITY,
  SURFACE_DOWNLOADS_AFTER_SCENE,
  SURFACE_DOWNLOADS_ATTRIBUTE,
  SURFACE_PRIORITY,
} from './inline-catalog';

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
    const connection = typeof navigator === 'undefined' ? undefined : navigator.connection;
    const slow = Boolean(connection) &&
      (connection.saveData === true || /^(?:slow-2g|2g|3g)$/.test(String(connection.effectiveType)));
    if (slow) element.setAttribute(${JSON.stringify(SURFACE_DOWNLOADS_ATTRIBUTE)}, ${JSON.stringify(SURFACE_DOWNLOADS_AFTER_SCENE)});
    const grid = catalog.grids[ref.web.grid_sha256];
    const root = new URL(base, document.baseURI);
    const preloads = [
      [ref.observations_available ? ref.observations_url : null, ${JSON.stringify(OBSERVATIONS_PRIORITY)}],
      [grid && grid.url, ${JSON.stringify(SURFACE_PRIORITY)}],
    ];
    if (!slow) preloads.push([ref.web.render.url, ${JSON.stringify(SURFACE_PRIORITY)}]);
    for (const [key, priority] of preloads) {
      if (!key) continue;
      const link = document.createElement('link');
      link.rel = 'preload';
      link.as = 'fetch';
      link.crossOrigin = 'anonymous';
      link.fetchPriority = priority;
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
