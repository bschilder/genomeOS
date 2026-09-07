/** Basemap, surface, and terrain presentation controls for Atlas design §11. */

import type { SceneCapabilities } from '../../atlas/scene/atlas-scene';
import type {
  BasemapId,
  ExplorerState,
  TerrainId,
} from '../../atlas/url-state';
import { defaultPalette, type PaletteId } from '../../atlas/visual-encoding';
import { InfoTip } from './InfoTip';

interface MapStyleControlsProps {
  capabilities: SceneCapabilities;
  disabled: boolean;
  state: ExplorerState;
  onBasemap: (value: BasemapId) => void;
  onCellEdges: (visible: boolean) => void;
  onPalette: (value: PaletteId) => void;
  onSurfaceOpacity: (value: number) => void;
  onTerrain: (value: TerrainId) => void;
}

const BASEMAPS: readonly [BasemapId, string][] = [
  ['dark-streets', 'Dark streets'],
  ['roads', 'Roads'],
  ['aerial', 'Aerial'],
  ['aerial-labels', 'Aerial + labels'],
];
const TERRAINS: readonly [TerrainId, string][] = [
  ['smooth-globe', 'Smooth globe'],
  ['world-terrain', 'World terrain'],
];
const PALETTES: readonly [PaletteId, string][] = [
  ['genome', 'Genome'],
  ['signal', 'Signal'],
  ['viridis', 'Viridis'],
  ['cividis', 'Cividis'],
  ['plasma', 'Plasma'],
];

export function MapStyleControls({
  capabilities,
  disabled,
  state,
  onBasemap,
  onCellEdges,
  onPalette,
  onSurfaceOpacity,
  onTerrain,
}: MapStyleControlsProps) {
  return (
    <div className="atlas-control-grid">
      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-basemap">Basemap</label>
          <InfoTip label="basemap">
            Geographic imagery beneath the scientific map. Cesium ion styles
            need the site’s read-only Cesium token.
          </InfoTip>
        </span>
        <select
          id="atlas-basemap"
          value={state.basemap}
          disabled={disabled}
          onChange={(event) => onBasemap(event.target.value as BasemapId)}
        >
          {BASEMAPS.map(([value, label]) => (
            <option
              value={value}
              key={value}
              disabled={!capabilities.basemaps[value]}
            >
              {label}
              {!capabilities.basemaps[value] ? ' (unavailable)' : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-physical-terrain">Physical terrain</label>
          <InfoTip label="physical terrain">
            Earth’s topography. This is separate from statistical elevation,
            which raises cells according to the selected metric.
          </InfoTip>
        </span>
        <select
          id="atlas-physical-terrain"
          value={state.terrain}
          disabled={disabled}
          onChange={(event) => onTerrain(event.target.value as TerrainId)}
        >
          {TERRAINS.map(([value, label]) => (
            <option
              value={value}
              key={value}
              disabled={!capabilities.terrains[value]}
            >
              {label}
              {!capabilities.terrains[value] ? ' (unavailable)' : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-surface-palette">Surface palette</label>
          <InfoTip label="surface palette">
            Color changes presentation only. Posterior estimates default to
            Genome; uncertainty defaults to Signal.
          </InfoTip>
        </span>
        <select
          id="atlas-surface-palette"
          value={state.surfacePalette}
          disabled={disabled}
          onChange={(event) => onPalette(event.target.value as PaletteId)}
        >
          {PALETTES.map(([value, label]) => (
            <option value={value} key={value}>
              {label}
              {value === defaultPalette(state.metric)
                ? ' (metric default)'
                : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="atlas-field atlas-field--range">
        <span className="atlas-field__title">
          <label htmlFor="atlas-surface-opacity">
            Surface opacity · {Math.round(state.surfaceOpacity * 100)}%
          </label>
          <InfoTip label="surface opacity">
            Lower opacity reveals more basemap context. It never changes the
            modeled values.
          </InfoTip>
        </span>
        <input
          id="atlas-surface-opacity"
          type="range"
          min="0.45"
          max="1"
          step="0.01"
          value={state.surfaceOpacity}
          disabled={disabled}
          onChange={(event) => onSurfaceOpacity(Number(event.target.value))}
        />
      </div>

      <div className="atlas-check-row">
        <label htmlFor="atlas-cell-edges">
          <input
            id="atlas-cell-edges"
            type="checkbox"
            checked={state.cellEdges}
            disabled={disabled}
            onChange={(event) => onCellEdges(event.target.checked)}
          />
          Cell edges
        </label>
        <InfoTip label="cell edges">
          Draws H3 top and vertical edges so elevated cells remain legible.
        </InfoTip>
      </div>
    </div>
  );
}
