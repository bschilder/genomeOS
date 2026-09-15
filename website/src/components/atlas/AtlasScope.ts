/** Scope controls and portals to one explorer when comparing maps (design §11). */

import { createContext, useContext } from 'react';

export const AtlasScope = createContext<string | null>(null);

export function useAtlasControlId(): (name: string) => string {
  const scope = useContext(AtlasScope);
  return (name) => (scope ? `${scope}-${name}` : name);
}

export function atlasPortalTarget(
  scope: string | null,
  selector: string,
): Element | null {
  const root = scope === null ? document : document.getElementById(scope);
  return root?.querySelector(selector) ?? null;
}
