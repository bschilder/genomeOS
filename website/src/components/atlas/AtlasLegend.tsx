/**
 * Compact scientific legend and expandable explanation for Atlas design §11;
 * on phones a one-row strip [label | ramp | info] (mobile sheets design
 * 2026-10-07 §A.1.7) whose popover closes on Escape.
 */

import { useRef, useState, type CSSProperties } from 'react';

import type { ArtifactRef } from '../../atlas/contracts';
import type { ExplorerState } from '../../atlas/url-state';
import { paletteStops } from '../../atlas/visual-encoding';
import { useEscapeLayer } from './useEscapeStack';

interface AtlasLegendProps {
  artifact: ArtifactRef;
  state: ExplorerState;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`;
}

export function AtlasLegend({ artifact, state }: AtlasLegendProps) {
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  // The popover joins the stack from the summary's click, not from the async `toggle`
  // event: click is a discrete React event, so the layer is registered before `open` is
  // even set and an Escape pressed right after opening closes the popover, not the layer
  // under it (§A.1.9: the popover is innermost). `onToggle` keeps the state in sync, and
  // the close callback resets it because Chromium can merge two toggle events into one.
  useEscapeLayer(
    infoOpen,
    () => {
      // Focus returns to the summary only from the legend itself or from <body>: an
      // Escape pressed inside another layer (the catalog's search box) closes the
      // popover without pulling focus out of that layer.
      const focused = document.activeElement;
      const returnFocus =
        !focused ||
        focused === document.body ||
        Boolean(details.current?.contains(focused));
      if (details.current) details.current.open = false;
      setInfoOpen(false);
      if (returnFocus) summary.current?.focus();
    },
    'popover',
  );
  const domain = artifact.metric_domains[state.metric];
  const isEstimate = state.metric === 'post_mean';
  const metricLabel = isEstimate ? 'Modeled frequency' : 'Model uncertainty';
  const shortLabel = isEstimate ? 'Frequency' : 'Uncertainty';
  const low = percent(domain[0]);
  const high = percent(domain[1]);
  const colors = paletteStops(state.surfacePalette);
  const scaleStyle = {
    '--atlas-scale': `linear-gradient(90deg, ${colors.join(', ')})`,
  } as CSSProperties;
  const priorStyle = {
    '--atlas-prior-scale': `linear-gradient(90deg, ${colors.join(', ')})`,
  } as CSSProperties;
  return (
    <aside className="atlas-legend" aria-label="Map legend">
      <div className="atlas-legend__compact">
        <strong>
          <span className="atlas-legend__label-full">{metricLabel}</span>
          <span className="atlas-legend__label-short" aria-hidden="true">
            {shortLabel}
          </span>
        </strong>
        <div
          className="atlas-color-scale"
          role="img"
          aria-label={`${metricLabel} color scale, ${low} to ${high}`}
        >
          <span>{low}</span>
          <i aria-hidden="true" style={scaleStyle} />
          <span>{high}</span>
        </div>
        <span className="atlas-legend__mode">
          {state.view === 'map'
            ? '2D'
            : state.elevation
              ? 'Color + height'
              : 'Color'}
        </span>
        <details
          className="atlas-legend__info"
          ref={details}
          onToggle={(event) => setInfoOpen(event.currentTarget.open)}
        >
          <summary
            aria-label="Explain the legend"
            ref={summary}
            onClick={() => setInfoOpen(!details.current?.open)}
          >
            i
          </summary>
          <div>
            <h2>
              {artifact.label}
              <span className="atlas-legend__heading-metric">
                {metricLabel}
              </span>
            </h2>
            <p>
              Color shows the modeled value. Dots mark estimates still driven
              mostly by the model’s starting assumptions because local evidence
              is limited; those cells are excluded from summaries. Neutral
              hatching means the value is unknown.
            </p>
            <div className="atlas-legend__keys">
              <span>
                <i className="atlas-key atlas-key--ring" /> Measurement
              </span>
              <span>
                <i className="atlas-key atlas-key--fill" /> Modeled surface
              </span>
              <span>
                <i className="atlas-key atlas-key--unknown" /> Unknown
              </span>
              <span>
                <i className="atlas-key atlas-key--prior" style={priorStyle} />{' '}
                Dots: mostly model assumptions
              </span>
            </div>
            <p className="atlas-legend__version">
              Model {artifact.model_version} · data {artifact.data_version} · H3
              resolution {artifact.resolution}
              {state.elevation &&
                state.view !== 'map' &&
                ` · height scale 0–${Math.round(180 * state.exaggeration)} km`}
            </p>
          </div>
        </details>
      </div>
    </aside>
  );
}
