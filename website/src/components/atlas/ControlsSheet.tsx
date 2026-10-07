/**
 * The explorer controls dock, restyled in place as the phone controls bottom
 * sheet (Atlas design §11; mobile sheets design 2026-10-07 §A.1.5). Desktop
 * renders the same single tree with no handle and a display: contents body.
 */

import { useId, type ReactNode } from 'react';

import { BottomSheetHandle } from './BottomSheetHandle';
import { dockedHeight, topChromeBottom } from './sheet-layout';
import { useBottomSheet } from './useBottomSheet';
import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery';

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
  const bodyId = useId();
  const sheet = useBottomSheet({
    dockedHeight: () => (explorer ? dockedHeight(explorer) : 0),
    enabled: isMobile,
    explorer,
    initial: 'peek',
    topChrome: () => (explorer ? topChromeBottom(explorer) : 0),
  });
  return (
    <aside
      aria-label="Explorer controls"
      className="atlas-controls"
      data-sheet-state={isMobile ? sheet.state : undefined}
      ref={sheet.sheetRef}
    >
      {isMobile && (
        <div className="atlas-sheet__peek" data-sheet-peek>
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
        </div>
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
