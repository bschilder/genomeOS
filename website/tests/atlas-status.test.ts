import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { AtlasStatus } from '../src/components/atlas/AtlasStatus';
import type { SceneFailure } from '../src/components/atlas/useAtlasSceneLifecycle';

function failurePanel(sceneFailure: SceneFailure): string {
  return renderToStaticMarkup(
    createElement(AtlasStatus, {
      status: 'loading artifact',
      activity: null,
      contextStatus: 'loading',
      sceneWarnings: [],
      corrections: [],
      error: null,
      sceneFailure,
      onRetry: () => {},
    }),
  );
}

describe('failure panels (Cesium globe design §12)', () => {
  it('says the map data failed, not the globe, when the data worker died', () => {
    // The globe loaded; its data worker died and only a reload starts a new one (fast-load §B.7).
    const html = failurePanel('worker');
    expect(html).toContain('role="alert"');
    expect(html).toContain('Map data unavailable');
    expect(html).toContain('The map data could not load');
    expect(html).toContain('Retrying reloads the page');
    expect(html).toContain('No scientific data was changed.');
    expect(html).not.toContain('globe could not load');
    expect(html).not.toContain('Globe unavailable');
    expect(html).not.toContain('Retry data');
    expect(html).toContain('Retry globe');
  });

  it('keeps the scene-chunk download panel for a globe that never loaded', () => {
    const html = failurePanel('download');
    expect(html).toContain('Globe unavailable');
    expect(html).toContain('The globe could not load');
    expect(html).toContain('Retrying reloads the page');
    expect(html).not.toContain('map data');
  });

  it('offers browser requirements only for WebGL', () => {
    const panels = (['webgl', 'download', 'render', 'worker'] as const).map(
      (failure) => [failure, failurePanel(failure)] as const,
    );
    for (const [failure, html] of panels)
      expect(html.includes('Browser requirements'), failure).toBe(
        failure === 'webgl',
      );
  });
});
