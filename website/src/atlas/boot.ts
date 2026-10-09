/**
 * Island-evaluation boot for Atlas design §11 and fast-load design §B.6: start the data worker and
 * the lazy Cesium scene chunk before React mounts, so neither waits for hydration.
 */

import { startAtlasWorker, type AtlasWorkerClient } from './worker/client';

export type AtlasSceneModule = typeof import('./scene/atlas-scene');

let worker: AtlasWorkerClient | null = null;
let sceneModule: Promise<AtlasSceneModule> | null = null;

/** The page's single data worker, started on first use. */
export function atlasWorker(): AtlasWorkerClient {
  worker ??= startAtlasWorker();
  return worker;
}

/**
 * The scene-chunk import shared by every caller. A failed import is cleared so the next call issues
 * a new `import()`, but Chromium answers that from its module map without a request, so the
 * explorer recovers from a failed download by reloading the page.
 */
export function loadAtlasSceneModule(): Promise<AtlasSceneModule> {
  if (!sceneModule) {
    const pending = import('./scene/atlas-scene');
    sceneModule = pending;
    pending.catch(() => {
      if (sceneModule === pending) sceneModule = null;
    });
  }
  return sceneModule;
}

/** Called once at island module evaluation; a no-op during server rendering. */
export function bootAtlas(): void {
  if (typeof window === 'undefined') return;
  atlasWorker();
  void loadAtlasSceneModule().catch(() => undefined);
}

/**
 * The provider's stall window override (fast-load design §B.2). Unset in every production build
 * (`assertRequestStallOverride` refuses it there), so the provider keeps its 15 s default; the e2e
 * build sets it so a browser test can hold a tier until it releases it.
 */
export function atlasRequestStallMs(): number | undefined {
  return Number(import.meta.env.PUBLIC_ATLAS_REQUEST_STALL_MS) || undefined;
}
