/**
 * Mutual exclusion of the inspector and the external "More info" panel on
 * phones (mobile sheets design 2026-10-07 §A.1.6): whichever opened most
 * recently is shown; opening one asks the other to close. Pure and DOM-free.
 */

export type PanelKind = 'inspector' | 'external';

interface PanelEntry {
  kind: PanelKind;
  close: () => void;
}

export interface PanelArbiter {
  present(kind: PanelKind, close: () => void): () => void;
  enforce(): void;
  open(): PanelKind | null;
}

export function createPanelArbiter(options: {
  exclusive: () => boolean;
  onChange: (open: PanelKind | null) => void;
}): PanelArbiter {
  let entries: PanelEntry[] = [];
  const latest = () => entries.at(-1)?.kind ?? null;
  const closeAllBut = (keep: PanelEntry) => {
    for (const entry of entries) if (entry !== keep) entry.close();
  };
  return {
    present(kind, close) {
      const entry = { close, kind };
      entries = [...entries.filter((other) => other.kind !== kind), entry];
      if (options.exclusive()) closeAllBut(entry);
      options.onChange(latest());
      return () => {
        entries = entries.filter((other) => other !== entry);
        options.onChange(latest());
      };
    },
    enforce() {
      const keep = entries.at(-1);
      if (keep && options.exclusive()) closeAllBut(keep);
    },
    open: latest,
  };
}
