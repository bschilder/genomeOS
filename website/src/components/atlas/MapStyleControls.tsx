/** Basemap, terrain, and globe presentation controls for Atlas design §11. */

import type { SceneCapabilities } from '../../atlas/scene/atlas-scene';
import type {
  BasemapId,
  ExplorerSceneMode,
  ExplorerState,
  TerrainId,
} from '../../atlas/url-state';
import { EarthStylePicker } from './EarthStylePicker';
import { InfoTip } from './InfoTip';

interface MapStyleControlsProps {
  capabilities: SceneCapabilities;
  disabled: boolean;
  state: ExplorerState;
  onBasemap: (value: BasemapId) => void;
  onBasemapBrightness: (value: number) => void;
  onBasemapOpacity: (value: number) => void;
  onCountryBorderColor: (value: string) => void;
  onCountryBorderOpacity: (value: number) => void;
  onDayNightLighting: (value: boolean) => void;
  onEarthOpacity: (value: number) => void;
  onOceanColor: (value: string) => void;
  onTerrain: (value: TerrainId) => void;
  onView: (view: ExplorerSceneMode) => void;
}

export function MapStyleControls({
  capabilities,
  disabled,
  state,
  onBasemap,
  onBasemapBrightness,
  onBasemapOpacity,
  onCountryBorderColor,
  onCountryBorderOpacity,
  onDayNightLighting,
  onEarthOpacity,
  onOceanColor,
  onTerrain,
  onView,
}: MapStyleControlsProps) {
  return (
    <div className="atlas-control-grid atlas-control-grid--map">
      <EarthStylePicker
        basemap={state.basemap}
        capabilities={capabilities}
        disabled={disabled}
        terrain={state.terrain}
        onBasemap={onBasemap}
        onTerrain={onTerrain}
      />

      <div className="atlas-map-imagery-style">
        <span className="atlas-field__title">
          <span>Basemap appearance</span>
          <InfoTip label="basemap appearance">
            Adjusts only the source map imagery. It does not alter the inferred
            surface or measured observations.
          </InfoTip>
        </span>
        <label className="atlas-field atlas-field--range">
          <span>Opacity · {Math.round(state.basemapOpacity * 100)}%</span>
          <input
            aria-label="Basemap opacity"
            type="range"
            min="0"
            max="100"
            step="1"
            value={Math.round(state.basemapOpacity * 100)}
            disabled={disabled}
            onChange={(event) =>
              onBasemapOpacity(Number(event.target.value) / 100)
            }
          />
        </label>
        <label className="atlas-field atlas-field--range">
          <span>Brightness · {Math.round(state.basemapBrightness * 100)}%</span>
          <input
            aria-label="Basemap brightness"
            type="range"
            min="0"
            max="100"
            step="1"
            value={Math.round(state.basemapBrightness * 100)}
            disabled={disabled}
            onChange={(event) =>
              onBasemapBrightness(Number(event.target.value) / 100)
            }
          />
        </label>
        <label className="atlas-color-control">
          <span className="atlas-field__title">
            <span>Ocean color</span>
            <InfoTip label="ocean color">
              Sets the globe color beneath translucent basemaps and imagery gaps
              without recoloring scientific layers.
            </InfoTip>
          </span>
          <input
            aria-label="Ocean color"
            type="color"
            value={state.oceanColor}
            disabled={disabled}
            onChange={(event) => onOceanColor(event.target.value)}
          />
        </label>
        <div className="atlas-check-row">
          <label htmlFor="atlas-day-night-lighting">
            <input
              id="atlas-day-night-lighting"
              type="checkbox"
              checked={state.dayNightLighting}
              disabled={disabled}
              onChange={(event) => onDayNightLighting(event.target.checked)}
            />
            Day/night lighting
          </label>
          <InfoTip label="day and night lighting">
            Shades the globe using Cesium’s current sun position. Turn it off to
            keep basemap brightness uniform worldwide.
          </InfoTip>
        </div>
      </div>

      <div className="atlas-field atlas-field--range">
        <span className="atlas-field__title">
          <label htmlFor="atlas-earth-opacity">
            Earth opacity · {Math.round(state.earthOpacity * 100)}%
          </label>
          <InfoTip label="Earth opacity">
            Controls the globe beneath every rendered layer. Full opacity
            prevents features on the far side of Earth from showing through.
          </InfoTip>
        </span>
        <input
          id="atlas-earth-opacity"
          type="range"
          min="0.15"
          max="1"
          step="0.01"
          value={state.earthOpacity}
          disabled={disabled}
          onChange={(event) => onEarthOpacity(Number(event.target.value))}
        />
      </div>

      <div className="atlas-country-border-style">
        <span className="atlas-field__title">
          <span>Country outlines</span>
          <InfoTip label="country outline style">
            Changes country-boundary color and transparency without changing the
            scientific surface.
          </InfoTip>
        </span>
        <label className="atlas-color-control">
          <span>Color</span>
          <input
            aria-label="Country outline color"
            type="color"
            value={state.countryBorderColor}
            disabled={disabled}
            onChange={(event) => onCountryBorderColor(event.target.value)}
          />
        </label>
        <label className="atlas-field atlas-field--range">
          <span>Opacity · {Math.round(state.countryBorderOpacity * 100)}%</span>
          <input
            aria-label="Country outline opacity"
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={state.countryBorderOpacity}
            disabled={disabled}
            onChange={(event) =>
              onCountryBorderOpacity(Number(event.target.value))
            }
          />
        </label>
      </div>

      <fieldset className="atlas-fieldset atlas-fieldset--view">
        <legend>
          View
          <InfoTip label="view">
            Globe is 3D, Map is flat, and Perspective is an angled 2.5D view.
            Statistical elevation requires an angled view.
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
    </div>
  );
}
