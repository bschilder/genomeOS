/**
 * Carries keyboard focus across a remount when the Atlas layout crosses 52rem
 * (mobile sheets design 2026-10-07 §A.1.4; focus never falls to <body>,
 * §A.1.6). The catalog picker and the dataset InfoTip change parent at the
 * switch (a portal into the top slot on phones, the dock on desktop), so React
 * unmounts the focused copy and mounts a new one, possibly one commit later:
 * each `useMediaQuery` owns its own MediaQueryList, so the sheet and the
 * controls switch in separate commits. A layout cleanup, which runs before
 * React removes the host node, records the key while the old copy still holds
 * focus; the new copy's mount effect takes focus back when nothing else has
 * it. A record lasts until the next task, so it cannot fire later.
 */

import { useLayoutEffect, useRef } from 'react';

const carried = new Set<string>();

/** Hands focus to the next copy of `key` that mounts in this task. */
export function carryFocus(key: string): void {
  carried.add(key);
  setTimeout(() => carried.delete(key), 0);
}

/** True while a remount in this task is about to take focus back. */
export function focusCarryPending(): boolean {
  return carried.size > 0;
}

function focusLost(): boolean {
  const active = document.activeElement;
  return !active || active === document.body;
}

/**
 * `scopes` are the nodes whose focus moves with this copy (a trigger and its
 * portalled dialog); `target` takes focus in the new copy. A null key opts out.
 */
export function useFocusCarry(
  key: string | null,
  scopes: () => readonly (Element | null)[],
  target: () => HTMLElement | null,
): void {
  const latest = useRef({ scopes, target });
  latest.current = { scopes, target };
  useLayoutEffect(() => {
    if (key === null) return;
    if (carried.delete(key) && focusLost())
      latest.current.target()?.focus({ preventScroll: true });
    return () => {
      const active = document.activeElement;
      if (
        active &&
        active !== document.body &&
        latest.current.scopes().some((scope) => scope?.contains(active))
      )
        carryFocus(key);
    };
  }, [key]);
}
