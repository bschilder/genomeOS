/** Scientific legend for Atlas design §11. */

import type { ArtifactRef } from '../../atlas/contracts';
import type { ExplorerState } from '../../atlas/url-state';

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
  return (
    <aside
      className={`atlas-legend atlas-legend--${state.metric}`}
      aria-label="Map legend"
    >
      <div className="atlas-legend__heading">
        <div>
          <p className="atlas-kicker">
            {isEstimate ? 'Modeled frequency' : 'Model uncertainty'}
          </p>
          <h2>{artifact.label}</h2>
        </div>
        <span>
          {state.view === 'map'
            ? '2D'
            : state.elevation
              ? 'Color + height'
              : 'Color'}
        </span>
      </div>
      <div className="atlas-color-scale" aria-label="Low to high color scale">
        <span>{percent(domain[0])}</span>
        <i aria-hidden="true" />
        <span>{percent(domain[1])}</span>
      </div>
      <div className="atlas-legend__keys">
        <span>
          <i className="atlas-key atlas-key--ring" />
          Measured observation
        </span>
        <span>
          <i className="atlas-key atlas-key--fill" />
          Modeled surface
        </span>
        <span>
          <i className="atlas-key atlas-key--unknown" />
          Unknown
        </span>
        <span>
          <i className="atlas-key atlas-key--prior" />
          Prior-dominated
        </span>
      </div>
      <p className="atlas-legend__note">
        Measurements and modeled estimates are separate layers. Unknown and
        prior-dominated cells are never included as numeric values.
      </p>
      <p className="atlas-legend__version">
        Model {artifact.model_version} · data {artifact.data_version} · H3
        resolution {artifact.resolution}
        {state.elevation &&
          state.view !== 'map' &&
          ` · height scale 0–${Math.round(180 * state.exaggeration)} km`}
      </p>
    </aside>
  );
}
