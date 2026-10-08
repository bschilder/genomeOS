import { describe, expect, it, vi } from 'vitest';

import {
  createMarkTracker,
  DISPLAYED_ATTRIBUTE,
} from '../src/atlas/scene/scene-marks';
import type { AtlasMark } from '../src/atlas/scene/types';
import { fakeRenderLoop } from './helpers/scene-fakes';

function harness() {
  const loop = fakeRenderLoop({ now: 0 });
  const attributes = new Map<string, string>();
  const perf = { mark: vi.fn() };
  const tracker = createMarkTracker(
    loop,
    { setAttribute: (name, value) => attributes.set(name, value) },
    perf,
  );
  const emitted: AtlasMark[] = [];
  tracker.onMark((mark) => emitted.push(mark));
  return { attributes, emitted, loop, perf, tracker };
}

describe('scene marks', () => {
  it('starts every readiness attribute at false', () => {
    const { attributes } = harness();
    expect(Object.fromEntries(attributes)).toEqual({
      'data-atlas-context-ready': 'false',
      'data-atlas-displayed': '',
      'data-atlas-edges-ready': 'false',
      'data-atlas-observations-visible': 'false',
      'data-atlas-surface-visible': 'false',
      'data-atlas-values-ready': 'false',
    });
  });

  it('emits a probed mark once, in postRender, with its attribute', () => {
    const { attributes, emitted, loop, perf, tracker } = harness();
    tracker.setProbe(() => ['observations-visible']);

    loop.frame();
    loop.frame();

    expect(perf.mark).toHaveBeenCalledTimes(1);
    expect(perf.mark).toHaveBeenCalledWith('atlas:observations-visible');
    expect(attributes.get('data-atlas-observations-visible')).toBe('true');
    expect(emitted).toEqual(['observations-visible']);
  });

  it('emits queued marks at the next frame, after probed marks', () => {
    const { emitted, loop, tracker } = harness();
    tracker.queue('ready');
    expect(loop.requestRender).toHaveBeenCalledTimes(1);
    expect(emitted).toEqual([]);
    tracker.setProbe(() => ['surface-visible']);

    loop.frame();

    expect(emitted).toEqual(['surface-visible', 'ready']);
  });

  it('re-arms epoch marks for a new artifact but not scene-wide marks', () => {
    const { emitted, loop, tracker } = harness();
    tracker.setProbe(() => ['surface-first-chunk']);
    tracker.queue('context-ready');
    loop.frame();

    tracker.beginEpoch();
    tracker.queue('context-ready');
    loop.frame();

    expect(emitted).toEqual([
      'surface-first-chunk',
      'context-ready',
      'surface-first-chunk',
    ]);
  });

  it('clears a displayed-artifact mark so it can fire again', () => {
    const { attributes, emitted, loop, tracker } = harness();
    tracker.queue('values-ready');
    loop.frame();
    tracker.clear('values-ready');
    expect(attributes.get('data-atlas-values-ready')).toBe('false');

    tracker.queue('values-ready');
    loop.frame();
    expect(attributes.get('data-atlas-values-ready')).toBe('true');
    expect(emitted).toEqual(['values-ready', 'values-ready']);
  });

  it('lists shown artifact ids sorted and without duplicates', () => {
    const { attributes, loop, tracker } = harness();
    tracker.setDisplayed(() => ['hbs-rs334', 'g6pd-deficiency', 'hbs-rs334']);
    loop.frame();
    expect(attributes.get(DISPLAYED_ATTRIBUTE)).toBe(
      'g6pd-deficiency hbs-rs334',
    );
  });

  it('detaches from postRender when destroyed', () => {
    const { emitted, loop, tracker } = harness();
    tracker.setProbe(() => ['observations-visible']);
    tracker.destroy();
    loop.frame();
    expect(emitted).toEqual([]);
    expect(loop.postRender.numberOfListeners).toBe(0);
  });
});
