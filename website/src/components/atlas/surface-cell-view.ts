/** Which surface-cell facts the hover preview and inspector may show (Atlas design §11; spec 2026-10-07 §B.2).
 *
 * Every number comes from the f64 detail tier through `cellAt`. Before that
 * tier loads, or when it is unavailable, only the cell id and the exact
 * support label (from the u8 render column) are shown.
 */

import type { Support, SurfaceCell } from '../../atlas/contracts';
import {
  cellAt,
  h3At,
  renderAt,
  type SurfaceArtifact,
} from '../../atlas/surface-columns';

export type DetailStatus = 'loading' | 'ready' | 'unavailable' | 'invalid';

export interface SurfaceSelection {
  kind: 'surface';
  artifactKey: string;
  row: number;
}

export type SurfaceCellView =
  | { state: 'values'; h3Index: string; support: Support; cell: SurfaceCell }
  | { state: 'loading' | 'unavailable'; h3Index: string; support: Support };

export const LOADING_CELL_VALUES = 'Loading cell values…';
export const CELL_VALUES_UNAVAILABLE = 'Cell values unavailable';
export const RETRY_CELL_VALUES = 'Retry cell values';

export function surfaceCellView(
  surface: SurfaceArtifact | null,
  selection: SurfaceSelection,
  detail: DetailStatus,
): SurfaceCellView | null {
  if (
    !surface ||
    surface.artifactKey !== selection.artifactKey ||
    detail === 'invalid' ||
    !Number.isInteger(selection.row) ||
    selection.row < 0 ||
    selection.row >= surface.grid.n
  )
    return null;
  const h3Index = h3At(surface, selection.row);
  const { support } = renderAt(surface, selection.row);
  if (detail === 'ready' && surface.detail)
    return {
      cell: cellAt(surface, selection.row),
      h3Index,
      state: 'values',
      support,
    };
  return {
    h3Index,
    state: detail === 'unavailable' ? 'unavailable' : 'loading',
    support,
  };
}
