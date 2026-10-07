/**
 * React wiring for the explorer panel arbiter (mobile sheets design
 * 2026-10-07 §A.1.6). Context, not props, because the external panel is
 * rendered by ExplorerControls but portaled into the rail.
 */

import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  createPanelArbiter,
  type PanelArbiter,
  type PanelKind,
} from './panel-arbiter';
import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery';

export type { PanelKind } from './panel-arbiter';

interface ExplorerPanels {
  arbiter: PanelArbiter;
  bodyInert: boolean;
  open: PanelKind | null;
  setBodyInert: (inert: boolean) => void;
}

const ExplorerPanelsContext = createContext<ExplorerPanels | null>(null);

export function ExplorerPanelsProvider({ children }: { children: ReactNode }) {
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const mobile = useRef(isMobile);
  mobile.current = isMobile;
  const [open, setOpen] = useState<PanelKind | null>(null);
  const [bodyInert, setBodyInert] = useState(false);
  const [arbiter] = useState(() =>
    createPanelArbiter({
      exclusive: () => mobile.current,
      onChange: setOpen,
    }),
  );
  useEffect(() => {
    if (isMobile) arbiter.enforce();
  }, [arbiter, isMobile]);
  const value = useMemo(
    () => ({ arbiter, bodyInert, open, setBodyInert }),
    [arbiter, bodyInert, open],
  );
  return createElement(ExplorerPanelsContext.Provider, { value }, children);
}

function usePanels(): ExplorerPanels {
  const panels = useContext(ExplorerPanelsContext);
  if (!panels)
    throw new Error(
      'Explorer panels must be used inside ExplorerPanelsProvider',
    );
  return panels;
}

/** Registers an open panel; on phones, opening it closes the other panel. */
export function useExplorerPanel(
  kind: PanelKind,
  open: boolean,
  close: () => void,
): void {
  const { arbiter } = usePanels();
  const latest = useRef(close);
  latest.current = close;
  useLayoutEffect(() => {
    if (!open) return;
    return arbiter.present(kind, () => latest.current());
  }, [arbiter, kind, open]);
}

export function useOpenPanel(): PanelKind | null {
  return usePanels().open;
}

export function usePanelBodyInert(): boolean {
  return usePanels().bodyInert;
}

export function useSetPanelBodyInert(): (inert: boolean) => void {
  return usePanels().setBodyInert;
}
