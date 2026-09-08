/** Inferred-surface presentation controls for Atlas design §11. */

import type {
  EdgeColorMode,
  ExplorerState,
  SurfaceGeometry,
} from '../../atlas/url-state';
import { defaultPalette, type PaletteId } from '../../atlas/visual-encoding';
import { InfoTip } from './InfoTip';

interface InferredSurfaceControlsProps {
  disabled: boolean;
  state: ExplorerState;
  onEdgeColorMode: (value: EdgeColorMode) => void;
  onEdgeFixedColor: (value: string) => void;
  onElevation: (enabled: boolean) => void;
  onExaggeration: (value: number) => void;
  onGeometry: (value: SurfaceGeometry) => void;
  onPalette: (value: PaletteId) => void;
  onSurfaceOpacity: (value: number) => void;
}

const PALETTES: readonly [PaletteId, string][] = [
  ['genome', 'Genome'],
  ['signal', 'Signal'],
  ['golden', 'Golden'],
  ['viridis', 'Viridis'],
  ['cividis', 'Cividis'],
  ['plasma', 'Plasma'],
  ['rainbow', 'Rainbow'],
];

export function InferredSurfaceControls({
  disabled,
  state,
  onEdgeColorMode,
  onEdgeFixedColor,
  onElevation,
  onExaggeration,
  onGeometry,
  onPalette,
  onSurfaceOpacity,
}: InferredSurfaceControlsProps) {
  return (
    <div className="atlas-control-grid atlas-control-grid--surface">
      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-surface-palette">Surface palette</label>
          <InfoTip label="surface palette">
            Color changes presentation only. Posterior estimates default to
            Rainbow; uncertainty defaults to Plasma.
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

      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-surface-geometry">Surface geometry</label>
          <InfoTip label="surface geometry">
            Triangles interpolate stored cell values. Hexagons preserve cells;
            Honmoon traces luminous value contours, with optional fill. All are
            renderings of the same posterior artifact.
          </InfoTip>
        </span>
        <select
          id="atlas-surface-geometry"
          value={state.surfaceGeometry}
          disabled={disabled}
          onChange={(event) =>
            onGeometry(event.target.value as SurfaceGeometry)
          }
        >
          <option value="triangles">Smooth triangles</option>
          <option value="hexagons">Flat hexagons</option>
          <option value="extruded">Extruded hexagons</option>
          <option value="honmoon">Honmoon</option>
          <option value="honmoon-fill">Honmoon (fill)</option>
        </select>
      </div>

      <div className="atlas-field atlas-field--range">
        <span className="atlas-field__title">
          <label htmlFor="atlas-surface-opacity">
            Surface opacity · {Math.round(state.surfaceOpacity * 100)}%
          </label>
          <InfoTip label="surface opacity">
            Controls the inferred surface and Honmoon intensity without changing
            modeled values.
          </InfoTip>
        </span>
        <input
          id="atlas-surface-opacity"
          type="range"
          min="0.2"
          max="1"
          step="0.01"
          value={state.surfaceOpacity}
          disabled={disabled}
          onChange={(event) => onSurfaceOpacity(Number(event.target.value))}
        />
      </div>

      {state.cellEdges && (
        <div className="atlas-edge-style">
          <label className="atlas-field">
            <span>Edge color</span>
            <select
              value={state.edgeColorMode}
              disabled={disabled}
              onChange={(event) =>
                onEdgeColorMode(event.target.value as EdgeColorMode)
              }
            >
              <option value="matched">Matched · brighter polygon color</option>
              <option value="fixed">Fixed</option>
            </select>
          </label>
          {state.edgeColorMode === 'fixed' && (
            <label className="atlas-color-control">
              <span>Fixed edge color</span>
              <input
                type="color"
                value={state.edgeFixedColor}
                disabled={disabled}
                onChange={(event) => onEdgeFixedColor(event.target.value)}
              />
            </label>
          )}
        </div>
      )}

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
            Raises supported cells using the displayed metric; it is not
            physical topography.
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
  );
}
