/** Load milestones as performance marks and readiness attributes for Atlas design §11 (spec 2026-10-07 §B.1).
 *
 * The scene renders on request, so each mark is taken in `scene.postRender`
 * and names the first frame that showed its milestone. Marks are mirrored as
 * `data-atlas-*` attributes on the explorer root for tests and the cold-load
 * harness.
 *
 * Cesium raises `postRender` outside its own try/catch, and a throw there stops
 * its render loop, so each probe, mark write and listener run from that event
 * is isolated: a throw is reported (`reportError`) and the rest of the frame's
 * marks still land. A new epoch also drops the previous artifact's pending
 * epoch marks, so they never stand in for the new artifact's. Once destroyed,
 * the tracker neither requests renders nor writes attributes.
 */

import type { AtlasMark } from './types';

export const MARK_ATTRIBUTES = {
  'context-ready': 'data-atlas-context-ready',
  'edges-ready': 'data-atlas-edges-ready',
  'observations-visible': 'data-atlas-observations-visible',
  'surface-visible': 'data-atlas-surface-visible',
  'values-ready': 'data-atlas-values-ready',
} as const;
export const DISPLAYED_ATTRIBUTE = 'data-atlas-displayed';
export const REVEAL_ATTRIBUTE = 'data-atlas-reveal';

const EPOCH_MARKS: readonly AtlasMark[] = [
  'observations-visible',
  'surface-first-chunk',
  'surface-visible',
  'ready',
];

export interface MarkTarget {
  setAttribute(name: string, value: string): void;
}

export interface MarkScene {
  postRender: { addEventListener(listener: () => void): () => void };
  requestRender(): void;
}

export interface MarkPerformance {
  mark(name: string, options?: PerformanceMarkOptions): unknown;
}

export interface MarkTracker {
  setProbe(probe: () => Iterable<AtlasMark>): void;
  setDisplayed(probe: () => readonly string[]): void;
  queue(mark: AtlasMark): void;
  clear(mark: AtlasMark): void;
  beginEpoch(): void;
  setAttribute(name: string, value: string): void;
  onMark(listener: (mark: AtlasMark) => void): () => void;
  destroy(): void;
}

function attributeFor(mark: AtlasMark): string | undefined {
  return (MARK_ATTRIBUTES as Partial<Record<AtlasMark, string>>)[mark];
}

/** Reports a throw like an uncaught one, without unwinding the caller. */
function reportMarkError(error: unknown): void {
  if (typeof globalThis.reportError === 'function')
    globalThis.reportError(error);
  else console.error('An Atlas load mark step failed.', error);
}

function attempt(step: () => void): void {
  try {
    step();
  } catch (error) {
    reportMarkError(error);
  }
}

export function createMarkTracker(
  scene: MarkScene,
  target: MarkTarget | null,
  perf: MarkPerformance = performance,
): MarkTracker {
  const emitted = new Set<AtlasMark>();
  // Insertion-ordered; a mark queued twice before a frame is emitted once.
  const queued = new Set<AtlasMark>();
  const listeners = new Set<(mark: AtlasMark) => void>();
  let probe: () => Iterable<AtlasMark> = () => [];
  let displayed: () => readonly string[] = () => [];
  let displayedValue = '';
  let destroyed = false;
  const write = (name: string, value: string) =>
    target?.setAttribute(name, value);
  for (const name of Object.values(MARK_ATTRIBUTES)) write(name, 'false');
  write(DISPLAYED_ATTRIBUTE, displayedValue);

  const emit = (mark: AtlasMark) => {
    if (destroyed || emitted.has(mark)) return;
    emitted.add(mark);
    attempt(() => perf.mark(`atlas:${mark}`));
    const attribute = attributeFor(mark);
    if (attribute) attempt(() => write(attribute, 'true'));
    for (const listener of [...listeners]) {
      // Like Cesium's Event: a listener removed (or the tracker destroyed)
      // during this emit is not called.
      if (listeners.has(listener)) attempt(() => listener(mark));
    }
  };
  const removePostRender = scene.postRender.addEventListener(() => {
    if (destroyed) return;
    attempt(() => {
      for (const mark of probe()) emit(mark);
    });
    const pending = [...queued];
    queued.clear();
    for (const mark of pending) emit(mark);
    if (destroyed) return;
    attempt(() => {
      const ids = [...new Set(displayed())].sort().join(' ');
      if (ids !== displayedValue) {
        write(DISPLAYED_ATTRIBUTE, ids);
        displayedValue = ids;
      }
    });
  });

  return {
    beginEpoch() {
      if (destroyed) return;
      // A pending epoch mark belongs to the previous artifact: it must neither
      // land in this epoch nor block this artifact's own mark.
      for (const mark of EPOCH_MARKS) {
        emitted.delete(mark);
        queued.delete(mark);
      }
    },
    clear(mark) {
      if (destroyed) return;
      emitted.delete(mark);
      queued.delete(mark);
      const attribute = attributeFor(mark);
      if (attribute) write(attribute, 'false');
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      removePostRender();
      listeners.clear();
      queued.clear();
      probe = () => [];
      displayed = () => [];
    },
    onMark(listener) {
      if (destroyed) return () => {};
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    queue(mark) {
      if (destroyed) return;
      queued.add(mark);
      scene.requestRender();
    },
    setAttribute(name, value) {
      if (destroyed) return;
      write(name, value);
    },
    setDisplayed(next) {
      if (destroyed) return;
      displayed = next;
    },
    setProbe(next) {
      if (destroyed) return;
      probe = next;
    },
  };
}
