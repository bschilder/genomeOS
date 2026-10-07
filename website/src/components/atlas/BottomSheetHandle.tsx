/**
 * The grab handle shared by the Atlas bottom sheets (mobile sheets design
 * 2026-10-07 §A.1.5). It has no children, so no portal event can bubble
 * through it; the grip is drawn by CSS.
 */

import { sheetStateLabel } from './sheet-geometry';
import type { SheetHandleProps, SheetState } from './useBottomSheet';

interface BottomSheetHandleProps {
  label: string;
  state: SheetState;
  controls: string;
  handleProps: SheetHandleProps;
}

export function BottomSheetHandle({
  controls,
  handleProps,
  label,
  state,
}: BottomSheetHandleProps) {
  return (
    <button
      {...handleProps}
      aria-controls={controls}
      aria-expanded={state !== 'peek'}
      aria-label={`${label}, ${sheetStateLabel(state)}`}
      className="atlas-sheet__handle"
      type="button"
    />
  );
}
