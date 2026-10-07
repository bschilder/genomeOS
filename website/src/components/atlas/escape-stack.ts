/**
 * One ordered Escape stack for the Atlas explorer (mobile sheets design
 * 2026-10-07 §A.1.9): each Escape closes only the innermost open layer —
 * popover, then dialog, then external panel, then inspector, then sheet.
 * Pure and DOM-free.
 */

export type EscapeLayerOrder =
  'popover' | 'dialog' | 'external' | 'inspector' | 'sheet';

export const ESCAPE_LAYER_ORDER: readonly EscapeLayerOrder[] = [
  'popover',
  'dialog',
  'external',
  'inspector',
  'sheet',
];

interface EscapeLayer {
  order: EscapeLayerOrder;
  close: () => void;
  sequence: number;
}

export interface EscapeKeyEvent {
  readonly key: string;
  readonly defaultPrevented: boolean;
  readonly isComposing?: boolean;
  preventDefault(): void;
  stopPropagation(): void;
}

export interface EscapeStack {
  register(order: EscapeLayerOrder, close: () => void): () => void;
  closeTop(): boolean;
  size(): number;
}

function rank(order: EscapeLayerOrder): number {
  return ESCAPE_LAYER_ORDER.indexOf(order);
}

export function createEscapeStack(): EscapeStack {
  const layers = new Set<EscapeLayer>();
  let sequence = 0;
  return {
    register(order, close) {
      sequence += 1;
      const layer = { order, close, sequence };
      layers.add(layer);
      return () => {
        layers.delete(layer);
      };
    },
    closeTop() {
      let top: EscapeLayer | null = null;
      for (const layer of layers) {
        if (
          !top ||
          rank(layer.order) < rank(top.order) ||
          (rank(layer.order) === rank(top.order) &&
            layer.sequence > top.sequence)
        ) {
          top = layer;
        }
      }
      if (!top) return false;
      layers.delete(top);
      top.close();
      return true;
    },
    size: () => layers.size,
  };
}

export function handleEscapeKey(
  stack: EscapeStack,
  event: EscapeKeyEvent,
): boolean {
  if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing)
    return false;
  if (!stack.closeTop()) return false;
  event.preventDefault();
  event.stopPropagation();
  return true;
}
