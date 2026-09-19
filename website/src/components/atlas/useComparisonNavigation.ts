/** Apply only camera/view state; scientific panel state stays independent (§11). */

import {
  useEffect,
  useRef,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react';
import { sameNavigation, type SharedNavigation } from '../../atlas/comparison';
import type { AtlasSceneController } from '../../atlas/scene/types';
import type { ExplorerState } from '../../atlas/url-state';

export function useComparisonNavigation(
  incoming: SharedNavigation | undefined,
  panel: 'left' | 'right' | undefined,
  ready: boolean,
  scene: RefObject<AtlasSceneController | null>,
  state: ExplorerState | null,
  setState: Dispatch<SetStateAction<ExplorerState | null>>,
  onError: (message: string) => void,
): void {
  const current = useRef(state);
  current.current = state;
  useEffect(() => {
    const controller = scene.current;
    if (
      !incoming ||
      incoming.source === panel ||
      !ready ||
      !controller ||
      !current.current
    )
      return;
    if (sameNavigation(incoming, current.current)) return;
    let cancelled = false;
    void (async () => {
      await controller.setSceneMode(incoming.view, true);
      if (cancelled) return;
      controller.setCamera(incoming.camera, false);
      setState((value) =>
        value
          ? { ...value, camera: incoming.camera, view: incoming.view }
          : value,
      );
    })().catch(() => {
      if (!cancelled)
        onError(
          'Camera synchronization failed. Scientific layers were not changed.',
        );
    });
    return () => {
      cancelled = true;
    };
  }, [incoming, panel, ready, scene, setState, onError]);
}
