/**
 * The inspector / More info rail, restyled in place as the phone panel sheet
 * (mobile sheets design 2026-10-07 §A.1.6). The external-panel portal slot is
 * always rendered here, so it is never moved or remounted. The sheet opens at
 * half; focus moves to Close when More info opens it and comes back to More
 * info or the globe on close, never to <body>. Crossing 52rem with a panel
 * open keeps focus on that panel when its focused control is hidden or
 * unmounted (Review Focus RF4).
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  type ReactNode,
} from 'react';

import { BottomSheetHandle } from './BottomSheetHandle';
import { dockedHeight, topChromeBottom } from './sheet-layout';
import { useBottomSheet } from './useBottomSheet';
import {
  useOpenPanel,
  usePanelBodyId,
  useSetPanelBodyInert,
  type PanelKind,
} from './useExplorerPanels';
import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery';

interface PanelSheetProps {
  children: ReactNode;
  explorer: HTMLElement | null;
}

const PANEL_LABELS: Record<PanelKind, string> = {
  external: 'External information',
  inspector: 'Selection details',
};

const PANELS: Record<PanelKind, string> = {
  external: '.atlas-external-details',
  inspector: ':scope > .atlas-inspector',
};

function panelIn(rail: HTMLElement | null, kind: PanelKind): Element | null {
  return rail?.querySelector(PANELS[kind]) ?? null;
}

function focusClose(rail: HTMLElement | null, kind: PanelKind): void {
  panelIn(rail, kind)
    ?.querySelector<HTMLElement>('.atlas-inspector__close')
    ?.focus();
}

function focusCanvas(explorer: HTMLElement | null): void {
  const canvas = explorer?.querySelector<HTMLElement>('.atlas-scene');
  if (!canvas) return;
  if (!canvas.hasAttribute('tabindex')) canvas.tabIndex = -1;
  canvas.focus({ preventScroll: true });
}

/**
 * A globe tap selects on pointerup, so the sheet opens under the finger and
 * the browser can hit-test that tap's click afterwards, onto the new handle,
 * Close or a link. Swallow a click whose pointer went down outside the rail;
 * keyboard and assistive-technology clicks (pointerId -1) always pass.
 */
function swallowGhostClicks(rail: HTMLElement): () => void {
  let down: { id: number; outside: boolean } | null = null;
  const onPointerDown = (event: PointerEvent) => {
    const target = event.target instanceof Node ? event.target : null;
    down = { id: event.pointerId, outside: !rail.contains(target) };
  };
  const onClick = (event: MouseEvent) => {
    if (!(event instanceof PointerEvent) || event.pointerId !== down?.id)
      return;
    const ghost = down.outside;
    down = null;
    if (!ghost) return;
    event.preventDefault();
    event.stopPropagation();
  };
  document.addEventListener('pointerdown', onPointerDown, true);
  rail.addEventListener('click', onClick, true);
  return () => {
    document.removeEventListener('pointerdown', onPointerDown, true);
    rail.removeEventListener('click', onClick, true);
  };
}

export function PanelSheet({ children, explorer }: PanelSheetProps) {
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const open = useOpenPanel();
  const setBodyInert = useSetPanelBodyInert();
  // The handle is rendered only while a panel is open, so the fallback is never named.
  const bodyId = usePanelBodyId(open ?? 'inspector');
  const rail = useRef<HTMLDivElement | null>(null);
  const previous = useRef<PanelKind | null>(null);
  const wasMobile = useRef(isMobile);
  const sheet = useBottomSheet({
    dockedHeight: () => (explorer ? dockedHeight(explorer) : 0),
    enabled: isMobile && open !== null,
    explorer,
    initial: 'half',
    topChrome: () => (explorer ? topChromeBottom(explorer) : 0),
  });
  const { bodyInert, setState, sheetRef } = sheet;
  const railRef = useCallback(
    (node: HTMLDivElement | null) => {
      rail.current = node;
      sheetRef(node);
    },
    [sheetRef],
  );

  useLayoutEffect(() => {
    setBodyInert(bodyInert);
  }, [bodyInert, setBodyInert]);

  useEffect(() => {
    if (!isMobile || !rail.current) return;
    return swallowGhostClicks(rail.current);
  }, [isMobile]);

  useLayoutEffect(() => {
    const prior = previous.current;
    const crossed = wasMobile.current !== isMobile;
    previous.current = open;
    wasMobile.current = isMobile;
    const active = document.activeElement;
    const onBody = !active || active === document.body;
    const controls = explorer?.querySelector('.atlas-controls');
    if (prior === open) {
      if (!crossed || !open) return;
      // Crossing 52rem with a panel open. Into the phone layout the controls
      // go hidden and inert, and the arbiter closes the other panel; out of
      // it the focused handle unmounts. Hidden and inert blur only at the
      // next rendering update, so this layout effect still sees the control
      // that is about to lose focus and moves it to the open panel first.
      const other = open === 'external' ? 'inspector' : 'external';
      const lost = isMobile
        ? Boolean(controls?.contains(active)) ||
          Boolean(panelIn(rail.current, other)?.contains(active))
        : onBody;
      if (lost) focusClose(rail.current, open);
      return;
    }
    if (open) setState('half');
    if (!isMobile) return;
    if (open === 'external') {
      focusClose(rail.current, open);
      return;
    }
    const lost =
      onBody ||
      Boolean(rail.current?.contains(active)) ||
      Boolean(controls?.contains(active));
    if (!lost) return;
    if (open === null && prior === 'external') {
      explorer
        ?.querySelector<HTMLElement>('.atlas-external-info__button')
        ?.focus();
      return;
    }
    focusCanvas(explorer);
  }, [explorer, isMobile, open, setState]);

  return (
    <div
      className="atlas-right-rail"
      data-sheet-state={isMobile && open ? sheet.state : undefined}
      ref={railRef}
    >
      {isMobile && open && (
        <div className="atlas-sheet__handle-row" data-sheet-peek>
          <BottomSheetHandle
            controls={bodyId}
            handleProps={sheet.handleProps}
            label={PANEL_LABELS[open]}
            state={sheet.state}
          />
        </div>
      )}
      {children}
      <div data-atlas-external-slot />
    </div>
  );
}
