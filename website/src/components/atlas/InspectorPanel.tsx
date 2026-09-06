/** Evidence-only pick inspector for Atlas design §11. */

import type {
  ArtifactRef,
  Observation,
  SurfaceCell,
} from '../../atlas/contracts';

export type InspectorSelection =
  | { kind: 'surface'; value: SurfaceCell }
  | { kind: 'observation'; value: Observation };

interface InspectorPanelProps {
  artifact: ArtifactRef;
  selection: InspectorSelection;
  onClose: () => void;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export function InspectorPanel({
  artifact,
  selection,
  onClose,
}: InspectorPanelProps) {
  if (selection.kind === 'surface') {
    const cell = selection.value;
    return (
      <aside className="atlas-inspector" aria-label="Selected map cell">
        <button
          className="atlas-inspector__close"
          type="button"
          onClick={onClose}
          aria-label="Close inspector"
        >
          ×
        </button>
        <p className="atlas-kicker">Modeled estimate</p>
        <h2>Inferred map cell</h2>
        <dl>
          <div>
            <dt>Posterior estimate</dt>
            <dd>{percent(cell.post_mean)}</dd>
          </div>
          <div>
            <dt>95% credible interval</dt>
            <dd>
              {percent(cell.q025)}–{percent(cell.q975)}
            </dd>
          </div>
          <div>
            <dt>Uncertainty</dt>
            <dd>{percent(cell.post_sd)}</dd>
          </div>
          <div>
            <dt>Evidence support</dt>
            <dd>{cell.support.replace('_', ' ')}</dd>
          </div>
          <div>
            <dt>Nearest measurement</dt>
            <dd>{Math.round(cell.dist_nearest_obs_km)} km</dd>
          </div>
          <div>
            <dt>Cell</dt>
            <dd>{cell.h3_index}</dd>
          </div>
        </dl>
        <p className="atlas-inspector__meta">
          Model {artifact.model_version}; data {artifact.data_version}; registry{' '}
          {artifact.registry_version}.
        </p>
      </aside>
    );
  }

  const observation = selection.value;
  return (
    <aside className="atlas-inspector" aria-label="Selected observation">
      <button
        className="atlas-inspector__close"
        type="button"
        onClick={onClose}
        aria-label="Close inspector"
      >
        ×
      </button>
      <p className="atlas-kicker">Measured observation</p>
      <h2>{observation.population_label}</h2>
      <dl>
        <div>
          <dt>Observed frequency</dt>
          <dd>{percent(observation.ac / observation.an)}</dd>
        </div>
        <div>
          <dt>Allele count</dt>
          <dd>
            {observation.ac} / {observation.an}
          </dd>
        </div>
        <div>
          <dt>Sampling radius</dt>
          <dd>{observation.radius_km.toFixed(1)} km</dd>
        </div>
        <div>
          <dt>Sampling design</dt>
          <dd>{observation.sampling_design.replaceAll('_', ' ')}</dd>
        </div>
        <div>
          <dt>Assay</dt>
          <dd>{observation.assay}</dd>
        </div>
        <div>
          <dt>Source location</dt>
          <dd>{observation.source_locator}</dd>
        </div>
      </dl>
      <p className="atlas-inspector__citation">{observation.citation_text}</p>
      <a href={observation.source_url} target="_blank" rel="noreferrer">
        View source data
      </a>
    </aside>
  );
}
