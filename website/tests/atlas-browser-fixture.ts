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
  artifacts: { n_cells: number }[];
}

const RENDER_CELL_BUDGET = 640;
const INSPECTOR_TARGET = { lat: 40.4407, lon: -3.7201 };

function compactSurface(
  payload: BrowserSurfaceArtifact,
): BrowserSurfaceArtifact {
  if (payload.cells.length <= RENDER_CELL_BUDGET) return payload;
  const inspectorCells = new Set(
    gridDisk(
      latLngToCell(
        INSPECTOR_TARGET.lat,
        INSPECTOR_TARGET.lon,
        payload.artifact.resolution,
      ),
      2,
    ),
  );
  const pinned = payload.cells.filter((cell) =>
    inspectorCells.has(cell.h3_index),
  );
  const remaining = payload.cells.filter(
    (cell) => !inspectorCells.has(cell.h3_index),
  );
  const slots = RENDER_CELL_BUDGET - pinned.length;
  const sampled = Array.from(
    { length: slots },
    (_, index) => remaining[Math.floor((index * remaining.length) / slots)],
  );
  const cells = [...pinned, ...sampled];
  return { ...payload, cells };
}

/**
 * Keep deterministic interaction/accessibility tests within a software-WebGL
 * geometry budget. APIRequestContext calls bypass these page routes, so tests
 * can and do assert the complete production artifact separately.
 */
export async function installAtlasBrowserFixture(page: Page): Promise<void> {
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.abort(),
  );
  await page.route('**/data/atlas/catalog.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserCatalog;
    const artifacts = payload.artifacts.map((artifact) => ({
      ...artifact,
      n_cells: Math.min(artifact.n_cells, RENDER_CELL_BUDGET),
    }));
    await route.fulfill({ response, json: { ...payload, artifacts } });
  });
  await page.route('**/data/atlas/*.surface.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserSurfaceArtifact;
    await route.fulfill({ response, json: compactSurface(payload) });
  });
}
