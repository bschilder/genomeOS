/**
 * Bottom-sheet state machine for the Atlas phone layout (mobile sheets design
 * 2026-10-07 §A.1.5): peek, half and full snaps, tap and keyboard cycling,
 * inert peek bodies, Escape back to peek, and the --atlas-sheet-offset /
 * --atlas-sheet-rest docking variables written on the explorer element.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type Ref,
  type RefCallback,
} from 'react';

import {
  nextSheetState,
  snapHeights,
  type SheetSnaps,
  type SheetState,
} from './sheet-geometry';
import {
  observeSheetLayout,
  peekHeight,
  writeDockedStack,
} from './sheet-layout';
import { useEscapeLayer } from './useEscapeStack';

export type { SheetState } from './sheet-geometry';

export interface BottomSheetOptions {
  initial: SheetState;
  enabled: boolean;
  explorer: HTMLElement | null;
  topChrome: () => number;
  dockedHeight: () => number;
}

export type SheetHandleProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  ref: Ref<HTMLButtonElement>;
};

export interface BottomSheet {
  state: SheetState;
  setState(state: SheetState): void;
  cycle(): void;
  handleProps: SheetHandleProps;
  sheetRef: RefCallback<HTMLElement>;
  bodyInert: boolean;
}

function writeSheetOffset(
  explorer: HTMLElement,
  px: number,
  rest: boolean,
): void {
  explorer.style.setProperty('--atlas-sheet-offset', `${px}px`);
  if (rest) explorer.style.setProperty('--atlas-sheet-rest', `${px}px`);
}

export function useBottomSheet(options: BottomSheetOptions): BottomSheet {
  const { enabled, explorer, initial } = options;
  const [state, setRawState] = useState<SheetState>(initial);
  const stateRef = useRef(state);
  stateRef.current = state;
  const measures = useRef(options);
  measures.current = options;
  const sheet = useRef<HTMLElement | null>(null);
  const handle = useRef<HTMLButtonElement | null>(null);
  const snaps = useRef<SheetSnaps | null>(null);

  const sheetRef = useCallback<RefCallback<HTMLElement>>((node) => {
    sheet.current = node;
  }, []);
  const handleRef = useCallback<RefCallback<HTMLButtonElement>>((node) => {
    handle.current = node;
  }, []);

  const settle = useCallback(() => {
    const root = sheet.current;
    if (!enabled || !explorer || !root) return;
    writeDockedStack(explorer);
    snaps.current = snapHeights({
      dockedHeight: measures.current.dockedHeight(),
      explorerHeight: explorer.clientHeight,
      peekHeight: peekHeight(root),
      topChromeBottom: measures.current.topChrome(),
    });
    writeSheetOffset(explorer, snaps.current[stateRef.current], true);
  }, [enabled, explorer]);

  useLayoutEffect(settle, [settle, state]);
  useEffect(() => {
    if (!enabled || !explorer) return;
    return observeSheetLayout(explorer, settle);
  }, [enabled, explorer, settle]);

  const setState = useCallback((next: SheetState) => {
    if (next === 'peek') {
      const active = document.activeElement;
      const bodies = sheet.current?.querySelectorAll('[data-sheet-body]');
      if (
        active &&
        bodies &&
        Array.from(bodies).some((body) => body.contains(active))
      )
        handle.current?.focus();
    }
    setRawState(next);
  }, []);
  const cycle = useCallback(
    () => setState(nextSheetState(stateRef.current)),
    [setState],
  );

  useEscapeLayer(enabled && state !== 'peek', () => setState('peek'), 'sheet');

  const handleProps: SheetHandleProps = {
    ref: handleRef,
    onClick: () => cycle(),
    onKeyDown: (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      if (!event.repeat) cycle();
    },
    onKeyUp: (event) => {
      // After a touch tap Chromium holds the button :active (~150 ms) and
      // dispatches a native click on Space keyup even though keydown was
      // cancelled; cancel the keyup so Space cycles exactly once.
      if (event.key === ' ') event.preventDefault();
    },
  };

  return {
    bodyInert: enabled && state === 'peek',
    cycle,
    handleProps,
    setState,
    sheetRef,
    state,
  };
}
