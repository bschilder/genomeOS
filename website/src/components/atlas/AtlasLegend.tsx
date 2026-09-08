/** Compact scientific legend and expandable explanation for Atlas design §11. */

import type { CSSProperties } from 'react';

import type { ArtifactRef } from '../../atlas/contracts';
import type { ExplorerState } from '../../atlas/url-state';
import { paletteStops } from '../../atlas/visual-encoding';

interface AtlasLegendProps {
  artifact: ArtifactRef;
  state: ExplorerState;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`;
}

export function AtlasLegend({ artifact, state }: AtlasLegendProps) {
  const domain = artifact.metric_domains[state.metric];
  const isEstimate = state.metric === 'post_mean';
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
          {isEstimate ? 'Modeled frequency' : 'Model uncertainty'}
        </strong>
        <div className="atlas-color-scale" aria-label="Low to high color scale">
          <span>{percent(domain[0])}</span>
          <i aria-hidden="true" style={scaleStyle} />
          <span>{percent(domain[1])}</span>
        </div>
        <span className="atlas-legend__mode">
          {state.view === 'map'
            ? '2D'
            : state.elevation
              ? 'Color + height'
              : 'Color'}
        </span>
        <details className="atlas-legend__info">
          <summary aria-label="Explain the legend">i</summary>
          <div>
            <h2>{artifact.label}</h2>
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
