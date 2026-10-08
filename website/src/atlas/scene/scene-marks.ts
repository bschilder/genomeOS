/** Load milestones as performance marks and readiness attributes for Atlas design §11 (spec 2026-10-07 §B.1).
 *
 * The scene renders on request, so each mark is taken in `scene.postRender`
 * and names the first frame that showed its milestone. Marks are mirrored as
 * `data-atlas-*` attributes on the explorer root for tests and the cold-load
 * harness.
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

export function createMarkTracker(
  scene: MarkScene,
  target: MarkTarget | null,
  perf: MarkPerformance = performance,
): MarkTracker {
  const emitted = new Set<AtlasMark>();
  const queued: AtlasMark[] = [];
  const listeners = new Set<(mark: AtlasMark) => void>();
  let probe: () => Iterable<AtlasMark> = () => [];
  let displayed: () => readonly string[] = () => [];
  let displayedValue = '';
  const write = (name: string, value: string) =>
    target?.setAttribute(name, value);
  for (const name of Object.values(MARK_ATTRIBUTES)) write(name, 'false');
  write(DISPLAYED_ATTRIBUTE, displayedValue);

  const emit = (mark: AtlasMark) => {
    if (emitted.has(mark)) return;
    emitted.add(mark);
    perf.mark(`atlas:${mark}`);
    const attribute = attributeFor(mark);
    if (attribute) write(attribute, 'true');
    for (const listener of [...listeners]) listener(mark);
  };
  const removePostRender = scene.postRender.addEventListener(() => {
    for (const mark of probe()) emit(mark);
    for (const mark of queued.splice(0)) emit(mark);
    const ids = [...new Set(displayed())].sort().join(' ');
    if (ids !== displayedValue) {
      displayedValue = ids;
      write(DISPLAYED_ATTRIBUTE, ids);
    }
  });

  return {
    beginEpoch() {
      for (const mark of EPOCH_MARKS) emitted.delete(mark);
    },
    clear(mark) {
      emitted.delete(mark);
      const index = queued.indexOf(mark);
      if (index >= 0) queued.splice(index, 1);
      const attribute = attributeFor(mark);
      if (attribute) write(attribute, 'false');
    },
    destroy() {
      removePostRender();
      listeners.clear();
    },
    onMark(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    queue(mark) {
      if (!queued.includes(mark)) queued.push(mark);
      scene.requestRender();
    },
    setAttribute(name, value) {
      write(name, value);
    },
    setDisplayed(next) {
      displayed = next;
    },
    setProbe(next) {
      probe = next;
    },
  };
}
