/** Accessible explorer controls for Atlas design §11. */

import type { AtlasCatalog, ExternalInfo } from '../../atlas/contracts';
import type {
  ObservationColorVariable,
  ObservationShape,
  ObservationSizeRange,
  ObservationSizeVariable,
} from '../../atlas/observation-encoding';
import type { SceneCapabilities } from '../../atlas/scene/atlas-scene';
import type {
  BasemapId,
  ExplorerSceneMode,
  ExplorerState,
  LayerId,
  TerrainId,
} from '../../atlas/url-state';
import type { Metric, PaletteId } from '../../atlas/visual-encoding';
import { InfoTip } from './InfoTip';
import { ExternalInfoPanel } from './ExternalInfoPanel';
import { MapStyleControls } from './MapStyleControls';
import { ObservationControls } from './ObservationControls';

interface ExplorerControlsProps {
  capabilities: SceneCapabilities;
  catalog: AtlasCatalog;
  dataBaseUrl: string;
  state: ExplorerState;
  disabled: boolean;
  onBasemap: (value: BasemapId) => void;
  onCellEdges: (visible: boolean) => void;
  onEntity: (id: string) => void;
  onExternalInfo: (
    source: 'gnomad' | 'dbsnp',
    signal: AbortSignal,
  ) => Promise<ExternalInfo>;
  onMetric: (metric: Metric) => void;
  onLayer: (layer: LayerId, visible: boolean) => void;
  onView: (view: ExplorerSceneMode) => void;
  onTerrain: (value: TerrainId) => void;
  onSurfacePalette: (value: PaletteId) => void;
  onSurfaceOpacity: (value: number) => void;
  onObservationColor: (value: ObservationColorVariable) => void;
  onObservationHemisphereRange: (value: ObservationSizeRange) => void;
  onObservationPointRange: (value: ObservationSizeRange) => void;
  onObservationShape: (value: ObservationShape) => void;
  onObservationSize: (value: ObservationSizeVariable) => void;
  onSamplingAreas: (visible: boolean) => void;
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
  capabilities,
  catalog,
  dataBaseUrl,
  state,
  disabled,
  onBasemap,
  onCellEdges,
  onEntity,
  onExternalInfo,
  onMetric,
  onLayer,
  onView,
  onTerrain,
  onSurfacePalette,
  onSurfaceOpacity,
  onObservationColor,
  onObservationHemisphereRange,
  onObservationPointRange,
  onObservationShape,
  onObservationSize,
  onSamplingAreas,
  onElevation,
  onExaggeration,
  onHome,
  onZoom,
}: ExplorerControlsProps) {
  const selectedArtifact = catalog.artifacts.find(
    (artifact) => artifact.id === state.entityId,
  );
  const observationsAvailable =
    selectedArtifact?.observations_available !== false;
  const downloadUrl = (path: string) =>
    `${dataBaseUrl.endsWith('/') ? dataBaseUrl : `${dataBaseUrl}/`}${path.replace(/^\/+/, '')}`;

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

      <div className="atlas-field atlas-field--entity">
        <span className="atlas-field__title">
          <label htmlFor="atlas-entity">Variant or phenotype</label>
          <InfoTip label="map selection">
            Choose a versioned genetic variant, allele, gene, or phenotype map
            from the public genomeOS catalog.
          </InfoTip>
        </span>
        <select
          id="atlas-entity"
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
      </div>

      {selectedArtifact && (
        <ExternalInfoPanel artifact={selectedArtifact} load={onExternalInfo} />
      )}

      <details className="atlas-control-sheet" open>
        <summary>Scientific layers</summary>
        <div className="atlas-control-sheet__body">
          <fieldset className="atlas-fieldset">
            <legend>
              Display
              <InfoTip label="displayed metric">
                Posterior estimate shows the modeled frequency. Uncertainty
                shows the model’s posterior standard deviation.
              </InfoTip>
            </legend>
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
            <legend>
              Layers
              <InfoTip label="map layers">
                Measurements and inferred values remain separate. Evidence
                support marks cells that cannot be treated as numeric results.
              </InfoTip>
            </legend>
            {(Object.keys(layerLabels) as LayerId[]).map((layer) => (
              <label key={layer}>
                <input
                  type="checkbox"
                  checked={
                    state.layers[layer] &&
                    !(layer === 'observations' && !observationsAvailable)
                  }
                  disabled={
                    disabled ||
                    (layer === 'observations' && !observationsAvailable)
                  }
                  onChange={(event) => onLayer(layer, event.target.checked)}
                />
                {layerLabels[layer]}
                {layer === 'observations' &&
                  !observationsAvailable &&
                  ' (not available yet)'}
              </label>
            ))}
          </fieldset>
        </div>
      </details>

      <details className="atlas-control-sheet">
        <summary>Map appearance</summary>
        <div className="atlas-control-sheet__body">
          <MapStyleControls
            capabilities={capabilities}
            disabled={disabled}
            state={state}
            onBasemap={onBasemap}
            onCellEdges={onCellEdges}
            onPalette={onSurfacePalette}
            onSurfaceOpacity={onSurfaceOpacity}
            onTerrain={onTerrain}
          />

          <fieldset className="atlas-fieldset atlas-fieldset--view">
            <legend>
              View
              <InfoTip label="view">
                Globe is 3D, Map is flat, and Perspective is an angled 2.5D
                view. Statistical elevation requires an angled view.
              </InfoTip>
            </legend>
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
            <div className="atlas-check-row">
              <label htmlFor="atlas-statistical-elevation">
                <input
                  id="atlas-statistical-elevation"
                  type="checkbox"
                  checked={state.elevation}
                  onChange={(event) => onElevation(event.target.checked)}
                />
                Statistical elevation
              </label>
              <InfoTip label="statistical elevation">
                Raises supported H3 cells using the currently displayed metric;
                it is not physical topography.
              </InfoTip>
            </div>
            <label className="atlas-field atlas-field--range">
              <span>{state.exaggeration.toFixed(1)}× height</span>
              <input
                type="range"
                min="0.25"
                max="5"
                step="0.25"
                value={state.exaggeration}
                disabled={!state.elevation}
                onChange={(event) => onExaggeration(Number(event.target.value))}
                aria-label="Height exaggeration"
              />
            </label>
          </div>
        </div>
      </details>

      <details className="atlas-control-sheet" hidden={!observationsAvailable}>
        <summary>Measured points</summary>
        <div className="atlas-control-sheet__body">
          <ObservationControls
            disabled={disabled || !observationsAvailable}
            state={state}
            onColor={onObservationColor}
            onHemisphereRange={onObservationHemisphereRange}
            onPointRange={onObservationPointRange}
            onSamplingAreas={onSamplingAreas}
            onShape={onObservationShape}
            onSize={onObservationSize}
          />
        </div>
      </details>

      {selectedArtifact && (
        <details className="atlas-control-sheet atlas-downloads">
          <summary>Download this dataset</summary>
          <div className="atlas-downloads__links">
            {Object.values(selectedArtifact.downloads)
              .filter((download) => download !== null)
              .map((download) => (
                <a
                  href={downloadUrl(download.url)}
                  download
                  key={download.url}
                  title={`SHA-256 ${download.sha256}`}
                >
                  {download.label}
                </a>
              ))}
          </div>
        </details>
      )}

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
          <p>
            Focus the globe, then use arrows or WASD to pan, +/− to zoom, and
            Q/E to tilt.
          </p>
        </details>
      </div>
    </aside>
  );
}
