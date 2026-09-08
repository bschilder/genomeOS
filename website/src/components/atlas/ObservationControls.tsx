/** Measured-observation presentation controls for Atlas design §11. */

import type {
  ObservationColorVariable,
  ObservationShape,
  ObservationSizeRange,
  ObservationSizeVariable,
} from '../../atlas/observation-encoding';
import {
  MAX_OBSERVATION_MARKER_SIZE,
  MIN_OBSERVATION_MARKER_SIZE,
} from '../../atlas/observation-encoding';
import type { ExplorerState } from '../../atlas/url-state';
import { InfoTip } from './InfoTip';

interface ObservationControlsProps {
  disabled: boolean;
  state: ExplorerState;
  onColor: (value: ObservationColorVariable) => void;
  onGradient: (value: readonly [string, string, string]) => void;
  onOpacity: (value: number) => void;
  onRange: (value: ObservationSizeRange) => void;
  onSamplingAreaColor: (value: string) => void;
  onShape: (value: ObservationShape) => void;
  onSize: (value: ObservationSizeVariable) => void;
  onSolidColor: (value: string) => void;
}

const SHAPES: readonly [ObservationShape, string][] = [
  ['circle', 'Circles'],
  ['hemisphere', 'Hemispheres'],
  ['pin', 'Pins'],
];
const COLORS: readonly [ObservationColorVariable, string][] = [
  ['solid', 'Solid'],
  ['gradient', 'Gradient'],
  ['study', 'Study'],
  ['ac', 'Allele count (AC)'],
];
const SIZES: readonly [ObservationSizeVariable, string][] = [
  ['fixed', 'Fixed'],
  ['frequency', 'Observed frequency'],
  ['ac', 'Allele count (AC)'],
  ['an', 'Allele denominator (AN)'],
];

export function ObservationControls({
  disabled,
  state,
  onColor,
  onGradient,
  onOpacity,
  onRange,
  onSamplingAreaColor,
  onShape,
  onSize,
  onSolidColor,
}: ObservationControlsProps) {
  const range = state.observationSizeRange;
  const setGradientStop = (index: 0 | 1 | 2, color: string) => {
    const next = [...state.observationGradient] as [string, string, string];
    next[index] = color;
    onGradient(next);
  };

  return (
    <div className="atlas-control-grid">
      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-marker-shape">Marker shape</label>
          <InfoTip label="marker shape">
            Three presentations of the same measured location. Circles and lit
            hemispheres keep the same apparent footprint.
          </InfoTip>
        </span>
        <select
          id="atlas-marker-shape"
          value={state.observationShape}
          disabled={disabled}
          onChange={(event) => onShape(event.target.value as ObservationShape)}
        >
          {SHAPES.map(([value, label]) => (
            <option value={value} key={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-marker-color">Marker color</label>
          <InfoTip label="marker color">
            Solid uses one chosen color. Gradient maps observed frequency
            through three chosen colors. Study is categorical; allele count uses
            a continuous scale.
          </InfoTip>
        </span>
        <select
          id="atlas-marker-color"
          value={state.observationColor}
          disabled={disabled}
          onChange={(event) =>
            onColor(event.target.value as ObservationColorVariable)
          }
        >
          {COLORS.map(([value, label]) => (
            <option value={value} key={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {state.observationColor === 'solid' && (
        <label className="atlas-color-control">
          <span>Solid marker color</span>
          <input
            type="color"
            value={state.observationSolidColor}
            disabled={disabled}
            onChange={(event) => onSolidColor(event.target.value)}
          />
        </label>
      )}

      {state.observationColor === 'gradient' && (
        <div
          className="atlas-gradient-control"
          role="group"
          aria-label="Marker gradient colors"
          style={
            {
              '--atlas-marker-gradient': `linear-gradient(90deg, ${state.observationGradient.join(', ')})`,
            } as React.CSSProperties
          }
        >
          <span>Observed-frequency colors</span>
          <div className="atlas-gradient-control__stops">
            {(['Low', 'Midpoint', 'High'] as const).map((label, index) => (
              <label key={label}>
                <span>{label}</span>
                <input
                  aria-label={`${label} gradient color`}
                  type="color"
                  value={state.observationGradient[index]}
                  disabled={disabled}
                  onChange={(event) =>
                    setGradientStop(index as 0 | 1 | 2, event.target.value)
                  }
                />
              </label>
            ))}
          </div>
          <span
            className="atlas-gradient-control__preview"
            aria-hidden="true"
          />
        </div>
      )}

      <div className="atlas-field atlas-field--range">
        <span className="atlas-field__title">
          <label htmlFor="atlas-marker-opacity">
            Marker opacity · {Math.round(state.observationOpacity * 100)}%
          </label>
          <InfoTip label="marker opacity">
            Changes marker transparency only; it does not change a measured
            frequency or the inferred surface.
          </InfoTip>
        </span>
        <input
          id="atlas-marker-opacity"
          type="range"
          min="0.1"
          max="1"
          step="0.01"
          value={state.observationOpacity}
          disabled={disabled}
          onChange={(event) => onOpacity(Number(event.target.value))}
        />
      </div>

      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-marker-size">Marker size</label>
          <InfoTip label="marker size">
            Size can be fixed or calculated from source-reported AC, AN, or
            observed frequency. Sampling radius is never used as a substitute.
          </InfoTip>
        </span>
        <select
          id="atlas-marker-size"
          value={state.observationSize}
          disabled={disabled}
          onChange={(event) =>
            onSize(event.target.value as ObservationSizeVariable)
          }
        >
          {SIZES.map(([value, label]) => (
            <option value={value} key={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div
        className="atlas-dual-range"
        role="group"
        aria-label="Marker size range"
      >
        <label>
          <span>Min · {Math.round(range[0])} px</span>
          <input
            type="range"
            min={MIN_OBSERVATION_MARKER_SIZE}
            max={MAX_OBSERVATION_MARKER_SIZE}
            step="1"
            value={range[0]}
            disabled={disabled}
            onChange={(event) =>
              onRange([
                Number(event.target.value),
                Math.max(Number(event.target.value), range[1]),
              ])
            }
          />
        </label>
        <label>
          <span>Max · {Math.round(range[1])} px</span>
          <input
            type="range"
            min={MIN_OBSERVATION_MARKER_SIZE}
            max={MAX_OBSERVATION_MARKER_SIZE}
            step="1"
            value={range[1]}
            disabled={disabled}
            onChange={(event) =>
              onRange([
                Math.min(Number(event.target.value), range[0]),
                Number(event.target.value),
              ])
            }
          />
        </label>
      </div>

      <label
        className="atlas-color-control"
        htmlFor="atlas-sampling-area-color"
      >
        <span>Observation radius color</span>
        <input
          id="atlas-sampling-area-color"
          type="color"
          value={state.samplingAreaColor}
          disabled={disabled}
          onChange={(event) => onSamplingAreaColor(event.target.value)}
        />
      </label>
    </div>
  );
}
