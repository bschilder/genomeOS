/**
 * Bottom-sheet state machine for the Atlas phone layout (mobile sheets design
 * 2026-10-07 §A.1.5): peek, half and full snaps, tap and keyboard cycling,
 * handle-only pointer drags (8 px slop, 120 ms projection, flicks that
 * settle at the next state at or beyond the release height, click
 * suppression after a drag), inert peek bodies, Escape back to peek,
 * and the --atlas-sheet-offset / --atlas-sheet-rest docking variables on the
 * explorer element — written once per animation frame while dragging, with
 * no React re-render.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type PointerEvent as ReactPointerEvent,
  type Ref,
  type RefCallback,
} from 'react';

import {
  DRAG_SLOP_PX,
  VelocityTracker,
  clampSheetHeight,
  nextSheetState,
  releaseSheetState,
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

interface DragSession {
  dragging: boolean;
  from: SheetState;
  height: number;
  pointerId: number;
  startHeight: number;
  startY: number;
  velocity: VelocityTracker;
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
  const drag = useRef<DragSession | null>(null);
  const frame = useRef(0);
  const suppressClick = useRef(false);

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
    if (!drag.current?.dragging)
      writeSheetOffset(explorer, snaps.current[stateRef.current], true);
  }, [enabled, explorer]);

  useLayoutEffect(settle, [settle, state]);
  useEffect(() => {
    if (!enabled || !explorer) return;
    return observeSheetLayout(explorer, settle);
  }, [enabled, explorer, settle]);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  // Entering peek: focus leaves the soon-inert body for the handle first.
  const releaseBodyFocus = useCallback(() => {
    const active = document.activeElement;
    const bodies = sheet.current?.querySelectorAll('[data-sheet-body]');
    if (
      active &&
      bodies &&
      Array.from(bodies).some((body) => body.contains(active))
    )
      handle.current?.focus();
  }, []);
  const setState = useCallback(
    (next: SheetState) => {
      if (next === 'peek') releaseBodyFocus();
      setRawState(next);
    },
    [releaseBodyFocus],
  );
  // `inert` follows `enabled` one commit late, so crossing into the phone
  // layout at peek moves focus to the (just mounted) handle before the body
  // goes inert; the follow-up render lands before paint.
  const [inertEnabled, setInertEnabled] = useState(false);
  useLayoutEffect(() => {
    if (enabled && stateRef.current === 'peek') releaseBodyFocus();
    setInertEnabled(enabled);
  }, [enabled, releaseBodyFocus]);
  const bodyInert = enabled && inertEnabled && state === 'peek';
  // Defence in depth: whatever path lands focus in the body during the
  // one-commit inert lag, it leaves for the handle as the body goes inert.
  useLayoutEffect(() => {
    if (bodyInert) releaseBodyFocus();
  }, [bodyInert, releaseBodyFocus]);
  const cycle = useCallback(
    () => setState(nextSheetState(stateRef.current)),
    [setState],
  );

  useEscapeLayer(enabled && state !== 'peek', () => setState('peek'), 'sheet');

  const finishDrag = (restState: SheetState) => {
    cancelAnimationFrame(frame.current);
    frame.current = 0;
    if (!explorer) return;
    explorer.removeAttribute('data-sheet-dragging');
    if (snaps.current)
      writeSheetOffset(explorer, snaps.current[restState], true);
  };

  // A drag that ends without pointerup returns to its pre-drag snap.
  const abortDrag = () => {
    const session = drag.current;
    if (!session) return;
    drag.current = null;
    if (handle.current?.hasPointerCapture(session.pointerId))
      handle.current.releasePointerCapture(session.pointerId);
    if (session.dragging) finishDrag(session.from);
  };

  const cancelDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerId === drag.current?.pointerId) abortDrag();
  };

  // Leaving the phone layout mid-drag unmounts the handle, and its
  // lostpointercapture then fires at the document, out of React's reach, so
  // the session ends here instead; otherwise the sheet keeps its drag height
  // and ignores every later pointerdown.
  useLayoutEffect(() => {
    if (!enabled || !explorer) return;
    return abortDrag;
  }, [enabled, explorer]);

  const handleProps: SheetHandleProps = {
    ref: handleRef,
    onClick: (event) => {
      if (suppressClick.current) {
        suppressClick.current = false;
        event.preventDefault();
        return;
      }
      cycle();
    },
    onKeyDown: (event) => {
      suppressClick.current = false;
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
    onLostPointerCapture: cancelDrag,
    onPointerCancel: cancelDrag,
    onPointerDown: (event) => {
      suppressClick.current = false;
      const current = snaps.current;
      if (!enabled || !current || drag.current) return;
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      const startHeight = current[stateRef.current];
      const velocity = new VelocityTracker();
      velocity.add(startHeight, event.timeStamp);
      drag.current = {
        dragging: false,
        from: stateRef.current,
        height: startHeight,
        pointerId: event.pointerId,
        startHeight,
        startY: event.clientY,
        velocity,
      };
    },
    onPointerMove: (event) => {
      const session = drag.current;
      const current = snaps.current;
      if (
        !session ||
        !current ||
        !explorer ||
        event.pointerId !== session.pointerId
      )
        return;
      if (
        !session.dragging &&
        Math.abs(event.clientY - session.startY) < DRAG_SLOP_PX
      )
        return;
      if (!session.dragging) {
        session.dragging = true;
        explorer.setAttribute('data-sheet-dragging', '');
      }
      session.height = clampSheetHeight(
        session.startHeight + session.startY - event.clientY,
        current,
      );
      session.velocity.add(session.height, event.timeStamp);
      if (frame.current) return;
      frame.current = requestAnimationFrame(() => {
        frame.current = 0;
        const live = drag.current;
        if (live?.dragging) writeSheetOffset(explorer, live.height, false);
      });
    },
    onPointerUp: (event) => {
      const session = drag.current;
      const current = snaps.current;
      if (!session || event.pointerId !== session.pointerId) return;
      drag.current = null;
      if (!session.dragging || !current) return;
      suppressClick.current = true;
      window.setTimeout(() => {
        suppressClick.current = false;
      }, 0);
      const next = releaseSheetState({
        height: session.height,
        snaps: current,
        velocity: session.velocity.velocity(event.timeStamp),
      });
      finishDrag(next);
      if (next !== stateRef.current) setState(next);
    },
  };

  return {
    bodyInert,
    cycle,
    handleProps,
    setState,
    sheetRef,
    state,
  };
}
