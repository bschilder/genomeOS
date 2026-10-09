import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { AtlasLegend } from '../src/components/atlas/AtlasLegend';
import { EscapeStackProvider } from '../src/components/atlas/useEscapeStack';
import type { ArtifactRef } from '../src/atlas/contracts';
import type { ExplorerState } from '../src/atlas/url-state';

const artifact = {
  data_version: 'map-2026-08',
  label: 'HbS (rs334)',
  metric_domains: { post_mean: [0.0008, 0.173], post_sd: [0.001, 0.05] },
  model_version: 'v3',
  resolution: 4,
} as unknown as ArtifactRef;

const state = {
  elevation: false,
  exaggeration: 1,
  metric: 'post_mean',
  surfacePalette: 'rainbow',
  view: 'globe',
} as unknown as ExplorerState;

function render(
  props: Partial<Parameters<typeof AtlasLegend>[0]> = {},
): string {
  // The legend registers its popover on the explorer's Escape stack.
  return renderToStaticMarkup(
    createElement(
      EscapeStackProvider,
      null,
      createElement(AtlasLegend, { artifact, state, ...props }),
    ),
  );
}

describe('legend follows the displayed layer', () => {
  it('uses the requested style when nothing has been committed', () => {
    const html = render();
    expect(html).toContain('Modeled frequency');
    expect(html).toContain('#6e40aa');
    expect(html).not.toContain('Loading map…');
  });

  it('keeps the committed metric and palette while a replacement builds', () => {
    const html = render({ layer: { metric: 'post_sd', palette: 'plasma' } });
    expect(html).toContain('Model uncertainty');
    expect(html).toContain('#0d0887');
    expect(html).not.toContain('#6e40aa');
  });

  it('marks a legend shown during the cold reveal as loading', () => {
    const html = render({ loading: true });
    expect(html).toContain('Loading map…');
    expect(html).toContain('data-atlas-legend-loading="true"');
    expect(html).toContain('role="status"');
  });
});
