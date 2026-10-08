/** Frame-budgeted overlay construction for Atlas design §11 (spec 2026-10-07 §B.6.9).
 *
 * Cell outlines and Natural Earth borders are added in slices of at most
 * `sliceMs` of main-thread work. Each slice ends with a render request and a
 * MessageChannel yield, which browsers do not clamp the way they clamp nested
 * `setTimeout(0)` calls.
 */

import type { ExplorerSceneMode } from '../url-state';

export type EdgeRenderer = 'buffer' | 'projected';

export const OVERLAY_SLICE_MS = 8;

export interface SliceOptions {
  sliceMs?: number;
  signal?: AbortSignal;
  onSlice?: () => void;
  now?: () => number;
  yieldFn?: () => Promise<void>;
}

// BufferPolylineCollection renders only in SceneMode.SCENE3D.
export function edgeRendererForMode(mode: ExplorerSceneMode): EdgeRenderer {
  return mode === 'globe' ? 'buffer' : 'projected';
}

export function abortError(
  message = 'Overlay construction was superseded',
): DOMException {
  return new DOMException(message, 'AbortError');
}

export function yieldToEventLoop(): Promise<void> {
  return new Promise((resolve) => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => {
      channel.port1.close();
      resolve();
    };
    channel.port2.postMessage(null);
  });
}

export async function runSliced(
  count: number,
  work: (index: number) => void,
  options: SliceOptions = {},
): Promise<number> {
  const sliceMs = options.sliceMs ?? OVERLAY_SLICE_MS;
  const now = options.now ?? (() => performance.now());
  const yieldFn = options.yieldFn ?? yieldToEventLoop;
  let index = 0;
  let slices = 0;
  while (index < count) {
    if (options.signal?.aborted) throw abortError();
    const started = now();
    do {
      work(index);
      index += 1;
    } while (index < count && now() - started < sliceMs);
    slices += 1;
    options.onSlice?.();
    if (index < count) {
      await yieldFn();
      if (options.signal?.aborted) throw abortError();
    }
  }
  return slices;
}
