import { gridDisk, latLngToCell } from 'h3-js';
import type { Page } from '@playwright/test';

interface BrowserSurfaceCell {
  h3_index: string;
  support: string;
}

interface BrowserSurfaceArtifact {
  artifact: { resolution: number };
  cells: BrowserSurfaceCell[];
}

interface BrowserCatalog {
  artifacts: {
    n_cells: number;
    n_observations: number;
    observations_url?: string;
    surface_url?: string;
  }[];
}

interface BrowserObservation {
  lat: number;
  lon: number;
}

interface BrowserObservationArtifact {
  observations: BrowserObservation[];
}

interface AtlasBrowserFixtureOptions {
  focus?: { lat: number; lon: number };
  observationBudget?: number;
  surfaceBudget?: number;
  surfaceScope?: 'distributed' | 'regional';
}

const RENDER_CELL_BUDGET = 256;
const RENDER_OBSERVATION_BUDGET = 64;
const INSPECTOR_TARGET = { lat: 40.4407, lon: -3.7201 };

function compactSurface(
  payload: BrowserSurfaceArtifact,
  options: AtlasBrowserFixtureOptions,
): BrowserSurfaceArtifact {
  const budget = options.surfaceBudget ?? RENDER_CELL_BUDGET;
  if (payload.cells.length <= budget) return payload;
  const focus = options.focus ?? INSPECTOR_TARGET;
  if (options.surfaceScope === 'regional') {
    const available = new Map(
      payload.cells.map((cell) => [cell.h3_index, cell] as const),
    );
    const center = latLngToCell(
      focus.lat,
      focus.lon,
      payload.artifact.resolution,
    );
    const selected = new Set<string>();
    for (let radius = 0; selected.size < budget && radius <= 30; radius += 1) {
      for (const h3Index of gridDisk(center, radius)) {
        if (available.has(h3Index)) selected.add(h3Index);
        if (selected.size === budget) break;
      }
    }
    if (selected.size < budget) {
      for (const cell of payload.cells) {
        selected.add(cell.h3_index);
        if (selected.size === budget) break;
      }
    }
    const cells = [...selected].map((h3Index) => available.get(h3Index)!);
    return { ...payload, cells };
  }
  const inspectorCells = new Set(
    gridDisk(
      latLngToCell(focus.lat, focus.lon, payload.artifact.resolution),
      2,
    ),
  );
  const pinned = payload.cells
    .filter((cell) => inspectorCells.has(cell.h3_index))
    .slice(0, budget);
  const remaining = payload.cells.filter(
    (cell) => !inspectorCells.has(cell.h3_index),
  );
  const slots = budget - pinned.length;
  const sampled = Array.from(
    { length: slots },
    (_, index) => remaining[Math.floor((index * remaining.length) / slots)],
  );
  const cells = [...pinned, ...sampled];
  return { ...payload, cells };
}

function compactObservations(
  payload: BrowserObservationArtifact,
  options: AtlasBrowserFixtureOptions,
): BrowserObservationArtifact {
  const budget = options.observationBudget ?? RENDER_OBSERVATION_BUDGET;
  if (payload.observations.length <= budget) return payload;
  const focus = options.focus ?? INSPECTOR_TARGET;
  const ordered = [...payload.observations].sort((left, right) => {
    const leftDistance =
      (left.lat - focus.lat) ** 2 + (left.lon - focus.lon) ** 2;
    const rightDistance =
      (right.lat - focus.lat) ** 2 + (right.lon - focus.lon) ** 2;
    return leftDistance - rightDistance;
  });
  const nearest = ordered.slice(0, Math.min(8, budget));
  const remaining = ordered.slice(8);
  const slots = budget - nearest.length;
  const sampled = Array.from(
    { length: slots },
    (_, index) => remaining[Math.floor((index * remaining.length) / slots)],
  );
  return { ...payload, observations: [...nearest, ...sampled] };
}

/**
 * Keep deterministic interaction/accessibility tests within a software-WebGL
 * geometry budget. APIRequestContext calls bypass these page routes, so tests
 * can and do assert the complete production artifact separately.
 */
export async function installAtlasBrowserFixture(
  page: Page,
  options: AtlasBrowserFixtureOptions = {},
): Promise<void> {
  const surfaceBudget = options.surfaceBudget ?? RENDER_CELL_BUDGET;
  const observationBudget =
    options.observationBudget ?? RENDER_OBSERVATION_BUDGET;
  // The row count the page's catalog states for each surface or observation file. The data routes
  // serve exactly that many rows, so they agree with the provider's row-count check whichever
  // catalog the build inlined: production's full counts, or the e2e catalog's 256 / 64.
  const statedRows = new Map<string, number>();
  const fileName = (url: string) => url.slice(url.lastIndexOf('/') + 1);
  const capCounts = (payload: BrowserCatalog): BrowserCatalog => ({
    ...payload,
    artifacts: payload.artifacts.map((artifact) => {
      const n_cells = Math.min(artifact.n_cells, surfaceBudget);
      const n_observations = Math.min(
        artifact.n_observations,
        observationBudget,
      );
      if (artifact.surface_url)
        statedRows.set(fileName(artifact.surface_url), n_cells);
      if (artifact.observations_url)
        statedRows.set(fileName(artifact.observations_url), n_observations);
      return { ...artifact, n_cells, n_observations };
    }),
  });
  const rowBudget = (requestUrl: string, budget: number) =>
    statedRows.get(fileName(new URL(requestUrl).pathname)) ?? budget;
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.abort(),
  );
  // Transitional (fast-load design §B.6.1): the catalog is inlined into /app/, so its counts are
  // rewritten in the document. The e2e fixture rewrite replaces this with ATLAS_CATALOG_PATH.
  await page.route(
    (url) => url.pathname.endsWith('/app/'),
    async (route) => {
      if (route.request().resourceType() !== 'document') {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const html = await response.text();
      const body = html.replace(
        /(<script\b[^>]*\bid="atlas-catalog"[^>]*>)([\s\S]*?)(<\/script>)/,
        (_match, open: string, json: string, close: string) => {
          const payload = capCounts(JSON.parse(json) as BrowserCatalog);
          return `${open}${JSON.stringify(payload).replace(/</g, '\\u003c')}${close}`;
        },
      );
      await route.fulfill({ body, response });
    },
  );
  await page.route('**/data/atlas/catalog.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserCatalog;
    await route.fulfill({ response, json: capCounts(payload) });
  });
  await page.route('**/data/atlas/*.surface.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserSurfaceArtifact;
    const budget = rowBudget(route.request().url(), surfaceBudget);
    await route.fulfill({
      response,
      json: compactSurface(payload, { ...options, surfaceBudget: budget }),
    });
  });
  await page.route('**/data/atlas/*.observations.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserObservationArtifact;
    const budget = rowBudget(route.request().url(), observationBudget);
    await route.fulfill({
      response,
      json: compactObservations(payload, {
        ...options,
        observationBudget: budget,
      }),
    });
  });
}
