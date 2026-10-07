/**
 * The inspector / More info rail, restyled in place as the phone panel sheet
 * (mobile sheets design 2026-10-07 §A.1.6). The external-panel portal slot is
 * always rendered here, so it is never moved or remounted. The sheet opens at
 * half; focus moves to Close when More info opens it and comes back to More
 * info or the globe on close, never to <body>.
 */

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  type ReactNode,
} from 'react';

import { BottomSheetHandle } from './BottomSheetHandle';
import { dockedHeight, topChromeBottom } from './sheet-layout';
import { useBottomSheet } from './useBottomSheet';
import {
  useOpenPanel,
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
  const railId = useId();
  const rail = useRef<HTMLDivElement | null>(null);
  const previous = useRef<PanelKind | null>(null);
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
    previous.current = open;
    if (prior === open) return;
    if (open) setState('half');
    if (!isMobile) return;
    if (open === 'external') {
      rail.current
        ?.querySelector<HTMLElement>(
          '.atlas-external-details .atlas-inspector__close',
        )
        ?.focus();
      return;
    }
    const active = document.activeElement;
    const controls = explorer?.querySelector('.atlas-controls');
    const lost =
      !active ||
      active === document.body ||
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
      id={railId}
      ref={railRef}
    >
      {isMobile && open && (
        <div className="atlas-sheet__handle-row" data-sheet-peek>
          <BottomSheetHandle
            controls={railId}
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
