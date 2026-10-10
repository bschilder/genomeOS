/**
 * Atlas usage events for GA4 (#422): which public dataset is open, which view is chosen and which
 * inspector opens. Never a coordinate, a cell or anything about the visitor.
 */

import { useEffect, useRef } from 'react';

import type { AtlasCatalog } from '../../atlas/contracts';
import type { ExplorerSceneMode } from '../../atlas/url-state';
import { trackEvent } from '../../lib/analytics';
import type { InspectorSelection } from './InspectorPanel';

export type InspectorKind = InspectorSelection['kind'];

interface AtlasAnalyticsInput {
  catalog: AtlasCatalog | null;
  /** The dataset the explorer state asks for. */
  entityId: string | undefined;
  /** The open inspector's kind, or undefined while none is open. */
  inspector: InspectorKind | undefined;
  view: ExplorerSceneMode | undefined;
}

/**
 * Record each dataset open, view switch and inspector open, once per action.
 *
 * - A dataset counts when the requested dataset changes, the first one included, and never again
 *   for a re-render or a data retry. Only an id the catalog lists counts, so a mistyped `?entity=`
 *   never reaches analytics.
 * - A view counts when it changes from the one before, whether the view control chose it or
 *   turning on elevation moved Map to Perspective. The view the page opened with is not a switch.
 * - An inspector counts when one opens or changes kind, not when another cell is picked in an open
 *   one.
 */
export function useAtlasAnalytics({
  catalog,
  entityId,
  inspector,
  view,
}: AtlasAnalyticsInput): void {
  const openDataset = useRef<string | null>(null);
  useEffect(() => {
    if (!entityId || entityId === openDataset.current) return;
    if (!catalog?.artifacts.some(({ id }) => id === entityId)) return;
    openDataset.current = entityId;
    trackEvent({
      name: 'atlas_dataset_open',
      params: { dataset_id: entityId },
    });
  }, [catalog, entityId]);

  const shownView = useRef<ExplorerSceneMode | null>(null);
  useEffect(() => {
    if (!view) return;
    const previous = shownView.current;
    shownView.current = view;
    if (previous !== null && previous !== view)
      trackEvent({ name: 'atlas_view_change', params: { view } });
  }, [view]);

  useEffect(() => {
    if (inspector)
      trackEvent({ name: 'atlas_inspector_open', params: { inspector } });
  }, [inspector]);
}
