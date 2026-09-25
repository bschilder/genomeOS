/** Navigation-only comparison contract (Atlas design §11; trait plan §4). */

import type { CameraState, ExplorerSceneMode } from './url-state';

export interface Navigation {
  camera: CameraState;
  view: ExplorerSceneMode;
}

export interface SharedNavigation extends Navigation {
  source: 'left' | 'right';
}

export function sameNavigation(a: Navigation, b: Navigation): boolean {
  if (a.view !== b.view) return false;
  return (Object.keys(a.camera) as (keyof CameraState)[]).every((key) => {
    const tolerance = key === 'height' ? 1 : 0.0001;
    const delta = Math.abs(a.camera[key] - b.camera[key]);
    const distance =
      key === 'heading' || key === 'lon'
        ? Math.abs(((delta + 180) % 360) - 180)
        : delta;
    return distance <= tolerance;
  });
}

export function comparisonQueries(
  search: string,
): { left: string; right: string } | null {
  const params = new URLSearchParams(search);
  const left = params.get('left');
  const right = params.get('right');
  if (left === null && right === null) return null;
  if (params.getAll('left').length > 1 || params.getAll('right').length > 1)
    throw new Error('Duplicate comparison selections are ambiguous.');
  if (!left || !right) throw new Error('Both map selections are required.');
  for (const query of [left, right]) {
    const panel = new URLSearchParams(query);
    if (
      panel.getAll('entity').length !== 1 ||
      panel.getAll('version').length !== 1 ||
      !panel.get('entity') ||
      !panel.get('version')
    )
      throw new Error(
        'Each map requires an explicit entity and artifact version.',
      );
  }
  return { left, right };
}

export function comparisonSearch(left: string, right: string): string {
  return new URLSearchParams({ left, right }).toString();
}
