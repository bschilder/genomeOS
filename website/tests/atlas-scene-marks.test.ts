import { afterEach, describe, expect, it, vi } from 'vitest';

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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

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

  it('keeps a throwing probe, mark or listener off the render loop', () => {
    const report = vi.fn();
    vi.stubGlobal('reportError', report);
    const { attributes, emitted, loop, perf, tracker } = harness();
    const listenerError = new Error('listener');
    const markError = new Error('perf.mark');
    tracker.onMark((mark) => {
      if (mark === 'ready') throw listenerError;
    });
    const after: AtlasMark[] = [];
    tracker.onMark((mark) => after.push(mark));
    perf.mark.mockImplementation((name: string) => {
      if (name === 'atlas:values-ready') throw markError;
    });
    tracker.queue('ready');
    tracker.queue('values-ready');
    tracker.queue('context-ready');

    expect(() => loop.frame()).not.toThrow();

    // Every queued mark lands, and the listener after the throwing one still runs.
    expect(emitted).toEqual(['ready', 'values-ready', 'context-ready']);
    expect(after).toEqual(['ready', 'values-ready', 'context-ready']);
    expect(attributes.get('data-atlas-values-ready')).toBe('true');
    expect(attributes.get('data-atlas-context-ready')).toBe('true');
    expect(report.mock.calls).toEqual([[listenerError], [markError]]);
  });

  it('still emits queued marks and the displayed ids when a probe throws', () => {
    const report = vi.fn();
    vi.stubGlobal('reportError', report);
    const { attributes, emitted, loop, tracker } = harness();
    const probeError = new Error('probe');
    tracker.setProbe(() => {
      throw probeError;
    });
    tracker.setDisplayed(() => ['hbs-rs334']);
    tracker.queue('context-ready');

    expect(() => loop.frame()).not.toThrow();

    expect(emitted).toEqual(['context-ready']);
    expect(attributes.get(DISPLAYED_ATTRIBUTE)).toBe('hbs-rs334');
    expect(report.mock.calls).toEqual([[probeError]]);

    const displayedError = new Error('displayed');
    tracker.setProbe(() => ['observations-visible']);
    tracker.setDisplayed(() => {
      throw displayedError;
    });
    expect(() => loop.frame()).not.toThrow();
    expect(emitted).toEqual(['context-ready', 'observations-visible']);
    expect(attributes.get(DISPLAYED_ATTRIBUTE)).toBe('hbs-rs334');
    expect(report.mock.calls).toEqual([[probeError], [displayedError]]);
  });

  it("drops the previous artifact's pending epoch marks at a new epoch", () => {
    const { emitted, loop, perf, tracker } = harness();
    // Artifact A commits, and B starts before A's next frame renders.
    tracker.queue('ready');
    tracker.queue('values-ready');
    tracker.beginEpoch();
    loop.frame();
    expect(emitted).toEqual(['values-ready']);

    // B's own ready is not blocked by A's.
    tracker.queue('ready');
    loop.frame();
    expect(emitted).toEqual(['values-ready', 'ready']);
    expect(perf.mark).toHaveBeenCalledTimes(2);
  });

  it('neither requests renders nor writes attributes once destroyed', () => {
    const { attributes, emitted, loop, tracker } = harness();
    const before = Object.fromEntries(attributes);
    tracker.destroy();

    tracker.queue('ready');
    tracker.clear('values-ready');
    tracker.setAttribute('data-atlas-reveal', '{}');
    tracker.beginEpoch();
    tracker.onMark((mark) => emitted.push(mark));
    loop.frame();

    expect(loop.requestRender).not.toHaveBeenCalled();
    expect(Object.fromEntries(attributes)).toEqual(before);
    expect(emitted).toEqual([]);
    expect(() => tracker.destroy()).not.toThrow();
  });

  it('stops a frame at destroy called from a mark listener', () => {
    const { emitted, loop, perf, tracker } = harness();
    tracker.onMark((mark) => {
      if (mark === 'ready') tracker.destroy();
    });
    const after: AtlasMark[] = [];
    tracker.onMark((mark) => after.push(mark));
    tracker.queue('ready');
    tracker.queue('context-ready');

    loop.frame();

    expect(emitted).toEqual(['ready']);
    expect(after).toEqual([]);
    expect(perf.mark).toHaveBeenCalledTimes(1);
  });
});
