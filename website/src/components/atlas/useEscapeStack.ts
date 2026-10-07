/**
 * React wiring for the explorer Escape stack (mobile sheets design 2026-10-07
 * §A.1.9): one capture-phase document keydown listener; pickers, panels,
 * popovers and sheets register while open.
 */

import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  createEscapeStack,
  handleEscapeKey,
  type EscapeLayerOrder,
  type EscapeStack,
} from './escape-stack';

export type { EscapeLayerOrder } from './escape-stack';

const EscapeStackContext = createContext<EscapeStack | null>(null);

export function EscapeStackProvider({ children }: { children: ReactNode }) {
  const [stack] = useState(createEscapeStack);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      handleEscapeKey(stack, event);
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [stack]);
  return createElement(EscapeStackContext.Provider, { value: stack }, children);
}

export function useEscapeLayer(
  active: boolean,
  close: () => void,
  order: EscapeLayerOrder,
): void {
  const stack = useContext(EscapeStackContext);
  if (!stack)
    throw new Error('useEscapeLayer must be used inside EscapeStackProvider');
  const latest = useRef(close);
  latest.current = close;
  useEffect(() => {
    if (!active) return;
    return stack.register(order, () => latest.current());
  }, [active, order, stack]);
}
