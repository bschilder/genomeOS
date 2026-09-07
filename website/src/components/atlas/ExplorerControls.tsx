/** Accessible explorer controls for Atlas design §11. */

import type { AtlasCatalog } from '../../atlas/contracts';
import type {
  ExplorerSceneMode,
  ExplorerState,
  LayerId,
} from '../../atlas/url-state';
import type { Metric } from '../../atlas/visual-encoding';

interface ExplorerControlsProps {
  catalog: AtlasCatalog;
  state: ExplorerState;
  disabled: boolean;
  onEntity: (id: string) => void;
  onMetric: (metric: Metric) => void;
  onLayer: (layer: LayerId, visible: boolean) => void;
  onView: (view: ExplorerSceneMode) => void;
  onElevation: (enabled: boolean) => void;
  onExaggeration: (value: number) => void;
  onHome: () => void;
  onZoom: (direction: 'in' | 'out') => void;
}

const layerLabels: Record<LayerId, string> = {
  context: 'Geographic context',
  observations: 'Measured observations',
  support: 'Evidence support',
  surface: 'Inferred surface',
};

export function ExplorerControls({
  catalog,
  state,
  disabled,
  onEntity,
  onMetric,
  onLayer,
  onView,
  onElevation,
  onExaggeration,
  onHome,
  onZoom,
}: ExplorerControlsProps) {
  const selectedArtifact = catalog.artifacts.find(
    (artifact) => artifact.id === state.entityId,
  );

  return (
    <aside className="atlas-controls" aria-label="Explorer controls">
      <div className="atlas-controls__intro">
        <p className="atlas-kicker">Interactive atlas</p>
        <h1>Explore human genetic variation</h1>
        <p>
          Compare measurements with modeled geographic patterns—and see where
          evidence ends.
        </p>
      </div>

      <label className="atlas-field atlas-field--entity">
        <span>Choose a map</span>
        <select
          value={state.entityId}
          disabled={disabled}
          onChange={(event) => onEntity(event.target.value)}
        >
          {!catalog.artifacts.some(
            (artifact) => artifact.id === state.entityId,
          ) && (
            <option value={state.entityId} disabled>
              Unavailable: {state.entityId}
            </option>
          )}
          {catalog.artifacts.map((artifact) => (
            <option value={artifact.id} key={artifact.id}>
              {artifact.label}
            </option>
          ))}
        </select>
      </label>

      <details className="atlas-control-sheet" open>
        <summary>Map controls</summary>
        <div className="atlas-control-sheet__body">
          <fieldset className="atlas-fieldset">
            <legend>Display</legend>
            <label>
              <input
                type="radio"
                name="metric"
                value="post_mean"
                checked={state.metric === 'post_mean'}
                onChange={() => onMetric('post_mean')}
              />
              Posterior estimate
            </label>
            <label>
              <input
                type="radio"
                name="metric"
                value="post_sd"
                checked={state.metric === 'post_sd'}
                onChange={() => onMetric('post_sd')}
              />
              Uncertainty
            </label>
          </fieldset>

          <fieldset className="atlas-fieldset atlas-fieldset--layers">
            <legend>Layers</legend>
            {(Object.keys(layerLabels) as LayerId[]).map((layer) => (
              <label key={layer}>
                <input
                  type="checkbox"
                  checked={
                    state.layers[layer] &&
                    !(
                      layer === 'observations' &&
                      selectedArtifact?.observations_available === false
                    )
                  }
                  disabled={
                    disabled ||
                    (layer === 'observations' &&
                      selectedArtifact?.observations_available === false)
                  }
                  onChange={(event) => onLayer(layer, event.target.checked)}
                />
                {layerLabels[layer]}
                {layer === 'observations' &&
                  selectedArtifact?.observations_available === false &&
                  ' (not available yet)'}
              </label>
            ))}
          </fieldset>

          <fieldset className="atlas-fieldset atlas-fieldset--view">
            <legend>View</legend>
            <div className="atlas-segments">
              {(['globe', 'map', 'perspective'] as ExplorerSceneMode[]).map(
                (view) => (
                  <label key={view}>
                    <input
                      type="radio"
                      name="view"
                      value={view}
                      checked={state.view === view}
                      onChange={() => onView(view)}
                    />
                    <span>{view[0].toUpperCase() + view.slice(1)}</span>
                  </label>
                ),
              )}
            </div>
          </fieldset>

          <div className="atlas-elevation">
            <label>
              <input
                type="checkbox"
                checked={state.elevation}
                onChange={(event) => onElevation(event.target.checked)}
              />
              Elevation
            </label>
            <label className="atlas-field atlas-field--range">
              <span>{state.exaggeration.toFixed(1)}× height</span>
              <input
                type="range"
                min="1"
                max="3"
                step="0.5"
                value={state.exaggeration}
                disabled={!state.elevation}
                onChange={(event) => onExaggeration(Number(event.target.value))}
                aria-label="Height exaggeration"
              />
            </label>
          </div>
        </div>
      </details>

      <div className="atlas-camera-actions" aria-label="Camera controls">
        <button
          type="button"
          onClick={onHome}
          title="Return to the global view"
        >
          Home
        </button>
        <button
          type="button"
          onClick={() => onZoom('in')}
          aria-label="Zoom in"
          title="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => onZoom('out')}
          aria-label="Zoom out"
          title="Zoom out"
        >
          −
        </button>
        <details className="atlas-keyboard-help">
          <summary role="button">Keys</summary>
          <p>Arrow keys or WASD pan. +/− zoom. Q/E tilt.</p>
        </details>
      </div>
    </aside>
  );
}
