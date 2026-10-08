/** Lazy Cesium scene lifecycle: create the scene once its chunk resolves (Atlas design §11; fast-load design §B.6.11). */

import { useEffect, useRef, useState, type RefObject } from 'react';

import { loadAtlasSceneModule } from '../../atlas/boot';
import { supportsWebGL } from '../../atlas/explorer-runtime';
import type { AtlasSceneController } from '../../atlas/scene/types';

export interface AtlasSceneLifecycleOptions {
  attempt: number;
  /** Subscribe to the new controller; returns the unsubscribe. */
  bind: (controller: AtlasSceneController) => () => void;
  cesiumToken: string;
  element: RefObject<HTMLDivElement | null>;
  /** Null until the catalog names the borders source; the scene waits for it. */
  naturalEarthUrl: string | null;
  onReset: () => void;
  onUnavailable: () => void;
  reducedMotion: boolean;
  scene: RefObject<AtlasSceneController | null>;
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
      onUnavailable();
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
            naturalEarthUrl,
            reducedMotion,
          });
          scene.current = controller;
          const unbind = bind(controller);
          release = () => {
            unbind();
            controller.destroy();
            if (scene.current === controller) scene.current = null;
          };
          setGeneration((value) => value + 1);
        } catch {
          onUnavailable();
        }
      },
      () => {
        if (active) onUnavailable();
      },
    );
    return () => {
      active = false;
      release?.();
    };
  }, [attempt, cesiumToken, naturalEarthUrl, reducedMotion]);

  return generation;
}
