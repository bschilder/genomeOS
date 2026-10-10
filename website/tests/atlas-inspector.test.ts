import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import { HoverPreview } from '../src/components/atlas/HoverPreview';
import { InspectorPanel } from '../src/components/atlas/InspectorPanel';
import { EscapeStackProvider } from '../src/components/atlas/useEscapeStack';
import { ExplorerPanelsProvider } from '../src/components/atlas/useExplorerPanels';
import { columnarSurface } from './helpers/columnar-surface';

const CELL = '83754efffffffff';
const artifact = {
  data_version: 'map-2026-08',
  model_version: 'v3',
  registry_version: 'fixture-registry',
} as unknown as ArtifactRef;
const loading = columnarSurface([
  { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'prior_dominated' },
]);
const loaded = columnarSurface(
  [{ h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'prior_dominated' }],
  { withDetail: true },
);
const selection = {
  artifactKey: loading.artifactKey,
  kind: 'surface' as const,
  row: 0,
};

/** InspectorPanel registers on the Escape stack and the phone panel sheet. */
function inExplorer(element: ReturnType<typeof createElement>): string {
  return renderToStaticMarkup(
    createElement(
      EscapeStackProvider,
      null,
      createElement(ExplorerPanelsProvider, null, element),
    ),
  );
}

function inspector(
  surface = loading,
  detail: 'loading' | 'ready' | 'unavailable' = 'loading',
) {
  return inExplorer(
    createElement(InspectorPanel, {
      artifact,
      detail,
      onClose: vi.fn(),
      onRetryDetail: vi.fn(),
      selection,
      surface,
    }),
  );
}

function hover(
  surface = loading,
  detail: 'loading' | 'ready' | 'unavailable' = 'loading',
) {
  return renderToStaticMarkup(
    createElement(HoverPreview, {
      detail,
      position: { x: 1, y: 2 },
      selection,
      surface,
    }),
  );
}

describe('inspector cell-value states', () => {
  it('shows the cell id and support but no number while values load', () => {
    const html = inspector();
    expect(html).toContain('Loading cell values…');
    expect(html).toContain('Cell ID');
    expect(html).toContain(CELL);
    expect(html).toContain('Mostly model assumptions (limited local data)');
    expect(html).not.toMatch(/\d\.\d{2}%/);
    expect(html).not.toMatch(/\d km/);
  });

  it('offers a retry when values are unavailable', () => {
    const html = inspector(loading, 'unavailable');
    expect(html).toContain('Cell values unavailable');
    expect(html).toContain('Retry cell values');
    expect(html).not.toMatch(/\d\.\d{2}%/);
  });

  it('prints every value from the detail tier once loaded', () => {
    const html = inspector(loaded, 'ready');
    expect(html).toContain('Posterior estimate');
    expect(html).toContain('50.00%');
    expect(html).toContain('45.00%–55.00%');
    expect(html).toContain('42 km');
    expect(html).not.toContain('Loading cell values…');
  });

  it('renders nothing for a selection of another artifact', () => {
    expect(
      inExplorer(
        createElement(InspectorPanel, {
          artifact,
          detail: 'ready',
          onClose: vi.fn(),
          selection: { ...selection, artifactKey: 'other:v3:map-2026-08' },
          surface: loaded,
        }),
      ),
    ).toBe('');
  });
});

describe('hover cell-value states', () => {
  it('shows the cell id and support label while values load', () => {
    const html = hover();
    expect(html).toContain('Loading cell values…');
    expect(html).toContain(CELL);
    expect(html).toContain('Mostly model assumptions (limited local data)');
    expect(html).not.toMatch(/\d\.\d{2}%/);
  });

  it('shows the unavailable state without a number', () => {
    const html = hover(loading, 'unavailable');
    expect(html).toContain('Cell values unavailable');
    expect(html).not.toMatch(/\d\.\d{2}%/);
  });

  it('keeps today’s preview once values load', () => {
    const html = hover(loaded, 'ready');
    expect(html).toContain('Posterior');
    expect(html).toContain('50.00%');
    expect(html).toContain('95% credible range');
  });
});
