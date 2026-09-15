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
  EdgeColorMode,
  ExplorerSceneMode,
  ExplorerState,
  LayerId,
  SurfaceGeometry,
  TerrainId,
} from '../../atlas/url-state';
import type { Metric, PaletteId } from '../../atlas/visual-encoding';
import { InfoTip } from './InfoTip';
import { ExternalInfoPanel } from './ExternalInfoPanel';
import { InferredSurfaceControls } from './InferredSurfaceControls';
import { MapStyleControls } from './MapStyleControls';
import { MapCatalogPicker } from './MapCatalogPicker';
import { ObservationControls } from './ObservationControls';

interface ExplorerControlsProps {
  capabilities: SceneCapabilities;
  catalog: AtlasCatalog;
  dataBaseUrl: string;
  state: ExplorerState;
  disabled: boolean;
  onBasemap: (value: BasemapId) => void;
  onBasemapBrightness: (value: number) => void;
  onBasemapOpacity: (value: number) => void;
  onCountryBorderColor: (value: string) => void;
  onCountryBorderOpacity: (value: number) => void;
  onDayNightLighting: (value: boolean) => void;
  onCellEdges: (visible: boolean) => void;
  onEdgeColorMode: (value: EdgeColorMode) => void;
  onEdgeFixedColor: (value: string) => void;
  onEarthOpacity: (value: number) => void;
  onOceanColor: (value: string) => void;
  onSurfaceGeometry: (value: SurfaceGeometry) => void;
  onEntity: (id: string) => void;
  onExternalInfo: (
    source: 'gnomad' | 'dbsnp' | 'alphagenome',
    signal: AbortSignal,
  ) => Promise<ExternalInfo>;
  onMetric: (metric: Metric) => void;
  onLayer: (layer: LayerId, visible: boolean) => void;
  onView: (view: ExplorerSceneMode) => void;
  onTerrain: (value: TerrainId) => void;
  onSurfacePalette: (value: PaletteId) => void;
  onSurfaceOpacity: (value: number) => void;
  onObservationColor: (value: ObservationColorVariable) => void;
  onObservationGradient: (value: readonly [string, string, string]) => void;
  onObservationOpacity: (value: number) => void;
  onObservationRange: (value: ObservationSizeRange) => void;
  onObservationShape: (value: ObservationShape) => void;
  onObservationSize: (value: ObservationSizeVariable) => void;
  onObservationSolidColor: (value: string) => void;
  onSamplingAreaColor: (value: string) => void;
  onSamplingAreas: (visible: boolean) => void;
  onElevation: (enabled: boolean) => void;
  onExaggeration: (value: number) => void;
  onHome: () => void;
  onZoom: (direction: 'in' | 'out') => void;
}

const layerLabels: Record<LayerId, string> = {
  context: 'Geography',
  countries: 'Country outlines',
  observations: 'Measured points',
  support: 'Evidence support',
  surface: 'Inferred surface',
};

const layerDescriptions: Record<LayerId, string> = {
  context:
    'Shows the selected basemap imagery and physical terrain beneath the scientific layers.',
  countries:
    'Shows country outlines and country names above the scientific surface. Their color and opacity are adjustable under Map.',
  observations:
    'Shows source-recorded measurements as markers. These are measured data, not model estimates.',
  support:
    'A dotted fill means nearby measurements did not outweigh the model’s starting assumptions. Its palette color still shows the estimate, but the cell is excluded from summaries. Neutral hatching means the value is unknown.',
  surface:
    'Shows the model’s inferred geographic pattern across supported cells, separately from measured points.',
};

export function ExplorerControls({
  capabilities,
  catalog,
  dataBaseUrl,
  state,
  disabled,
  onBasemap,
  onBasemapBrightness,
  onBasemapOpacity,
  onCountryBorderColor,
  onCountryBorderOpacity,
  onDayNightLighting,
  onCellEdges,
  onEdgeColorMode,
  onEdgeFixedColor,
  onEarthOpacity,
  onOceanColor,
  onSurfaceGeometry,
  onEntity,
  onExternalInfo,
  onMetric,
  onLayer,
  onView,
  onTerrain,
  onSurfacePalette,
  onSurfaceOpacity,
  onObservationColor,
  onObservationGradient,
  onObservationOpacity,
  onObservationRange,
  onObservationShape,
  onObservationSize,
  onObservationSolidColor,
  onSamplingAreaColor,
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
        <p className="atlas-kicker atlas-kicker--brand">
          <span className="brand-name">genomeOS</span> Atlas
        </p>
        <h1>Explore human genetic variation</h1>
        <p>
          Visualize measured and predicted allele frequencies across the world
        </p>
      </div>

      <div className="atlas-field atlas-field--entity">
        <span className="atlas-field__title">
          <span>Select dataset</span>
          <InfoTip label="map selection">
            Choose a versioned genetic variant, allele, gene, or phenotype map
            from the public genomeOS catalog.
          </InfoTip>
        </span>
        <MapCatalogPicker
          catalog={catalog}
          disabled={disabled}
          selectedId={state.entityId}
          onSelect={onEntity}
        />
      </div>

      {selectedArtifact && (
        <ExternalInfoPanel artifact={selectedArtifact} load={onExternalInfo} />
      )}

      <details className="atlas-control-sheet" open>
        <summary>Scientific layers</summary>
        <div className="atlas-control-sheet__body">
          <fieldset className="atlas-fieldset atlas-fieldset--display">
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
            {(['context', 'countries', 'observations'] as LayerId[]).map(
              (layer) => (
                <div className="atlas-layer-row" key={layer}>
                  <InfoTip label={`${layerLabels[layer]} layer`}>
                    {layerDescriptions[layer]}
                  </InfoTip>
                  <label>
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
                </div>
              ),
            )}
            <div className="atlas-layer-row">
              <InfoTip label="observation radii">
                Outlines the source-supported geographic precision. Very large
                rings mean the source located a sample only to a broad
                administrative area.
              </InfoTip>
              <label htmlFor="atlas-sampling-areas">
                <input
                  id="atlas-sampling-areas"
                  type="checkbox"
                  checked={state.samplingAreas && observationsAvailable}
                  disabled={disabled || !observationsAvailable}
                  onChange={(event) => onSamplingAreas(event.target.checked)}
                />
                Observation radii
              </label>
            </div>
            {(['support', 'surface'] as LayerId[]).map((layer) => (
              <div className="atlas-layer-row" key={layer}>
                <InfoTip label={`${layerLabels[layer]} layer`}>
                  {layerDescriptions[layer]}
                </InfoTip>
                <label>
                  <input
                    type="checkbox"
                    checked={state.layers[layer]}
                    disabled={disabled}
                    onChange={(event) => onLayer(layer, event.target.checked)}
                  />
                  {layerLabels[layer]}
                </label>
              </div>
            ))}
            <div className="atlas-layer-row">
              <InfoTip label="cell outlines">
                Draws a visible outline around every rendered map polygon.
              </InfoTip>
              <label htmlFor="atlas-cell-edges">
                <input
                  id="atlas-cell-edges"
                  type="checkbox"
                  checked={state.cellEdges}
                  disabled={disabled}
                  onChange={(event) => onCellEdges(event.target.checked)}
                />
                Cell outlines
              </label>
            </div>
          </fieldset>
        </div>
      </details>

      <details className="atlas-control-sheet">
        <summary>Map</summary>
        <div className="atlas-control-sheet__body">
          <MapStyleControls
            capabilities={capabilities}
            disabled={disabled}
            state={state}
            onBasemap={onBasemap}
            onBasemapBrightness={onBasemapBrightness}
            onBasemapOpacity={onBasemapOpacity}
            onCountryBorderColor={onCountryBorderColor}
            onCountryBorderOpacity={onCountryBorderOpacity}
            onDayNightLighting={onDayNightLighting}
            onEarthOpacity={onEarthOpacity}
            onOceanColor={onOceanColor}
            onTerrain={onTerrain}
            onView={onView}
          />
        </div>
      </details>

      <details className="atlas-control-sheet">
        <summary>Inferred surface</summary>
        <div className="atlas-control-sheet__body">
          <InferredSurfaceControls
            disabled={disabled}
            state={state}
            onEdgeColorMode={onEdgeColorMode}
            onEdgeFixedColor={onEdgeFixedColor}
            onElevation={onElevation}
            onExaggeration={onExaggeration}
            onGeometry={onSurfaceGeometry}
            onPalette={onSurfacePalette}
            onSurfaceOpacity={onSurfaceOpacity}
          />
        </div>
      </details>

      <details className="atlas-control-sheet" hidden={!observationsAvailable}>
        <summary>Measured points</summary>
        <div className="atlas-control-sheet__body">
          <ObservationControls
            disabled={disabled || !observationsAvailable}
            state={state}
            onColor={onObservationColor}
            onGradient={onObservationGradient}
            onOpacity={onObservationOpacity}
            onRange={onObservationRange}
            onSamplingAreaColor={onSamplingAreaColor}
            onShape={onObservationShape}
            onSize={onObservationSize}
            onSolidColor={onObservationSolidColor}
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
