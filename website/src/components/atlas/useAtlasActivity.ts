/** Shared Atlas operation lifecycle for Atlas design §11. */

import { useRef, useState, type RefObject } from 'react';

import type {
  ExplorerActivity,
  ExplorerLoadStatus,
} from '../../atlas/progress';
import type {
  AtlasSceneController,
  SceneProgressListener,
} from '../../atlas/scene/atlas-scene';

export function nextPaint(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

export function useAtlasActivity(
  scene: RefObject<AtlasSceneController | null>,
  onError: (error: unknown) => void,
) {
  const sequence = useRef(0);
  const [status, setStatus] = useState<ExplorerLoadStatus>('loading catalog');
  const [activity, setActivity] = useState<ExplorerActivity | null>({
    detail: 'Waiting for the catalog response',
    label: 'Loading catalog',
    progress: null,
  });

  const begin = (
    nextStatus: Exclude<ExplorerLoadStatus, 'ready'>,
    nextActivity: ExplorerActivity,
  ): number => {
    const id = ++sequence.current;
    setStatus(nextStatus);
    setActivity(nextActivity);
    return id;
  };
  const update = (id: number, nextActivity: ExplorerActivity) => {
    if (id === sequence.current) setActivity(nextActivity);
  };
  const finish = (id: number) => {
    if (id !== sequence.current) return;
    setActivity(null);
    setStatus('ready');
  };
  const fail = (id: number) => {
    if (id === sequence.current) setActivity(null);
  };
  const runScene = (
    label: string,
    detail: string,
    operation: (
      controller: AtlasSceneController,
      progress: SceneProgressListener,
    ) => Promise<unknown>,
  ): (() => void) | undefined => {
    const controller = scene.current;
    if (!controller) return undefined;
    const id = begin('rendering', { detail, label, progress: null });
    let canceled = false;
    void nextPaint()
      .then(() => {
        if (canceled || controller !== scene.current) return;
        return operation(controller, (renderProgress) => {
          if (canceled) return;
          update(id, { label, ...renderProgress });
        });
      })
      .then(() => {
        if (!canceled && controller === scene.current) finish(id);
      })
      .catch((caught) => {
        if (canceled) return;
        fail(id);
        onError(caught);
      });
    return () => {
      canceled = true;
    };
  };

  return { activity, begin, fail, finish, runScene, status, update };
}
