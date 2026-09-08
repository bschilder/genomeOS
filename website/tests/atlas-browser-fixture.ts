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
  artifacts: { n_cells: number; n_observations: number }[];
}

interface BrowserObservation {
  lat: number;
  lon: number;
}

interface BrowserObservationArtifact {
  observations: BrowserObservation[];
}

const RENDER_CELL_BUDGET = 256;
const RENDER_OBSERVATION_BUDGET = 64;
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

function compactObservations(
  payload: BrowserObservationArtifact,
): BrowserObservationArtifact {
  if (payload.observations.length <= RENDER_OBSERVATION_BUDGET) return payload;
  const ordered = [...payload.observations].sort((left, right) => {
    const leftDistance =
      (left.lat - INSPECTOR_TARGET.lat) ** 2 +
      (left.lon - INSPECTOR_TARGET.lon) ** 2;
    const rightDistance =
      (right.lat - INSPECTOR_TARGET.lat) ** 2 +
      (right.lon - INSPECTOR_TARGET.lon) ** 2;
    return leftDistance - rightDistance;
  });
  const nearest = ordered.slice(0, 8);
  const remaining = ordered.slice(8);
  const slots = RENDER_OBSERVATION_BUDGET - nearest.length;
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
      n_observations: Math.min(
        artifact.n_observations,
        RENDER_OBSERVATION_BUDGET,
      ),
    }));
    await route.fulfill({ response, json: { ...payload, artifacts } });
  });
  await page.route('**/data/atlas/*.surface.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserSurfaceArtifact;
    await route.fulfill({ response, json: compactSurface(payload) });
  });
  await page.route('**/data/atlas/*.observations.json', async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as BrowserObservationArtifact;
    await route.fulfill({ response, json: compactObservations(payload) });
  });
}
