/** Lazy Cesium scene lifecycle: create the scene once its chunk resolves (Atlas design §11; fast-load design §B.6.11). */

import { useEffect, useRef, useState, type RefObject } from 'react';

import { loadAtlasSceneModule } from '../../atlas/boot';
import { supportsWebGL } from '../../atlas/explorer-runtime';
import type { AtlasSceneController } from '../../atlas/scene/types';
import type { AtlasWorkerClient } from '../../atlas/worker/client';

/**
 * Why the globe or its data is unavailable (Cesium globe design §12). `webgl`: no WebGL, or Cesium
 * failed to start. `download`: the scene chunk failed to load. Chromium keeps a failed dynamic
 * import in the page's module map and rejects every later `import()` of that URL without a
 * request, so only a page reload recovers. `render`: a frame threw and the scene's render loop
 * stopped (`AtlasSceneController.onRenderError`); Cesium's document-wide geometry workers keep a
 * failed import, so that too recovers only through a reload. `worker`: the Atlas data worker died
 * after it started (its module script failed to download, or it threw;
 * `AtlasWorkerClient.onCrash`). The globe may be up, but the page's one data worker cannot be
 * restarted under the scene and provider that share it, so only a reload recovers (fast-load design
 * §B.7, amended). This hook reports `webgl` and `download`; the explorer reports the rest.
 */
export type SceneFailure = 'webgl' | 'download' | 'render' | 'worker';

export interface AtlasSceneLifecycleOptions {
  attempt: number;
  /** Subscribe to the new controller; returns the unsubscribe. */
  bind: (controller: AtlasSceneController) => () => void;
  cesiumToken: string;
  element: RefObject<HTMLDivElement | null>;
  /** Null until the catalog names the borders source; the scene waits for it. */
  naturalEarthUrl: string | null;
  onReset: () => void;
  onUnavailable: (failure: Extract<SceneFailure, 'webgl' | 'download'>) => void;
  reducedMotion: boolean;
  scene: RefObject<AtlasSceneController | null>;
  /** `.atlas-explorer`, which receives the readiness attributes (fast-load design §B.1). */
  markTarget: HTMLElement | null;
  /** The worker the provider was built with: it already holds each decoded grid and render tier. */
  worker: AtlasWorkerClient;
}

/** Returns a counter that increments every time a new scene controller becomes available. */
export function useAtlasSceneLifecycle(
  options: AtlasSceneLifecycleOptions,
): number {
  const [generation, setGeneration] = useState(0);
  const latest = useRef(options);
  latest.current = options;
  const { attempt, cesiumToken, naturalEarthUrl, reducedMotion } = options;

  useEffect(() => {
    const { bind, element, onReset, onUnavailable, scene } = latest.current;
    const container = element.current;
    if (!container) return;
    onReset();
    if (!supportsWebGL()) {
      onUnavailable('webgl');
      return;
    }
    if (!naturalEarthUrl) return;
    let active = true;
    let release: (() => void) | null = null;
    loadAtlasSceneModule().then(
      ({ createAtlasScene }) => {
        if (!active) return;
        try {
          const controller = createAtlasScene(container, {
            cesiumToken,
            markTarget: latest.current.markTarget,
            naturalEarthUrl,
            reducedMotion,
            worker: latest.current.worker,
          });
          scene.current = controller;
          const unbind = bind(controller);
          release = () => {
            unbind();
            controller.destroy();
            if (scene.current === controller) scene.current = null;
          };
          setGeneration((value) => value + 1);
        } catch (error) {
          console.error('The Atlas globe could not start.', error);
          onUnavailable('webgl');
        }
      },
      (error: unknown) => {
        if (!active) return;
        console.error('The Atlas globe scene could not be loaded.', error);
        onUnavailable('download');
      },
    );
    return () => {
      active = false;
      release?.();
    };
  }, [attempt, cesiumToken, naturalEarthUrl, reducedMotion]);

  return generation;
}
