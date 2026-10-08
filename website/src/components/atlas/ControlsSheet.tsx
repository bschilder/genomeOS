/**
 * The explorer controls dock, restyled in place as the phone controls bottom
 * sheet (Atlas design §11; mobile sheets design 2026-10-07 §A.1.5). Desktop
 * renders the same single tree with no handle and a display: contents body.
 * While a panel sheet is open on a phone the controls are inert and hidden,
 * keeping their snap state for when the panel closes (§A.1.6). Widening out
 * of the phone layout gives the unmounted handle's focus to the dataset
 * trigger instead of <body>.
 */

import {
  useCallback,
  useId,
  useLayoutEffect,
  useRef,
  type ReactNode,
  type RefObject,
} from 'react';

import { BottomSheetHandle } from './BottomSheetHandle';
import { dockedHeight, topChromeBottom } from './sheet-layout';
import { useBottomSheet } from './useBottomSheet';
import { useOpenPanel } from './useExplorerPanels';
import { carryFocus, focusCarryPending } from './useFocusCarry';
import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery';

const TABBABLE =
  'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])';

/**
 * The handle and summary row, rendered only on phones. Leaving the phone
 * layout unmounts them; the layout cleanup runs before React removes the row,
 * so it can still see whether the row held focus.
 */
function SheetPeek({
  children,
  heldFocus,
}: {
  children: ReactNode;
  heldFocus: RefObject<boolean>;
}) {
  const row = useRef<HTMLDivElement>(null);
  useLayoutEffect(
    () => () => {
      const active = document.activeElement;
      heldFocus.current = Boolean(active && row.current?.contains(active));
    },
    [heldFocus],
  );
  return (
    <div className="atlas-sheet__peek" data-sheet-peek ref={row}>
      {children}
    </div>
  );
}

/**
 * The peek row held focus and is gone. Unless a remount is taking focus back
 * (the dataset InfoTip's carry), it goes to the dataset trigger: directly in
 * the dock, or, while the trigger is still in the top slot about to move
 * there, through the catalog's focus carry.
 */
function restoreFocusAfterWidening(
  aside: HTMLElement | null,
  explorer: HTMLElement | null,
): void {
  const active = document.activeElement;
  if ((active && active !== document.body) || focusCarryPending()) return;
  const trigger = explorer?.querySelector<HTMLElement>(
    '.atlas-map-catalog__trigger:not(:disabled)',
  );
  if (trigger?.closest('.atlas-top-slot')) {
    carryFocus('catalog');
    return;
  }
  (trigger ?? aside?.querySelector<HTMLElement>(TABBABLE))?.focus({
    preventScroll: true,
  });
}

interface ControlsSheetProps {
  children: ReactNode;
  explorer: HTMLElement | null;
  peekExtra?: ReactNode;
  summary: string;
}

export function ControlsSheet({
  children,
  explorer,
  peekExtra,
  summary,
}: ControlsSheetProps) {
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const panelOpen = useOpenPanel() !== null;
  const hidden = isMobile && panelOpen;
  const bodyId = useId();
  const sheet = useBottomSheet({
    dockedHeight: () => (explorer ? dockedHeight(explorer) : 0),
    enabled: isMobile && !panelOpen,
    explorer,
    initial: 'peek',
    topChrome: () => (explorer ? topChromeBottom(explorer) : 0),
  });
  const aside = useRef<HTMLElement | null>(null);
  const { sheetRef } = sheet;
  const asideRef = useCallback(
    (node: HTMLElement | null) => {
      aside.current = node;
      sheetRef(node);
    },
    [sheetRef],
  );
  const peekHeldFocus = useRef(false);
  useLayoutEffect(() => {
    if (isMobile || !peekHeldFocus.current) return;
    peekHeldFocus.current = false;
    restoreFocusAfterWidening(aside.current, explorer);
  }, [explorer, isMobile]);
  return (
    <aside
      aria-label="Explorer controls"
      className="atlas-controls"
      data-sheet-state={isMobile ? sheet.state : undefined}
      hidden={hidden}
      inert={hidden}
      ref={asideRef}
    >
      {isMobile && (
        <SheetPeek heldFocus={peekHeldFocus}>
          <div className="atlas-sheet__handle-row">
            <BottomSheetHandle
              controls={bodyId}
              handleProps={sheet.handleProps}
              label="Explorer controls"
              state={sheet.state}
            />
            {peekExtra}
          </div>
          <p className="atlas-sheet__summary">{summary}</p>
        </SheetPeek>
      )}
      <div
        className="atlas-sheet__body"
        data-sheet-body
        id={bodyId}
        inert={sheet.bodyInert}
      >
        {children}
      </div>
    </aside>
  );
}
