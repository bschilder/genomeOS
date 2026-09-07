/** Measured-observation presentation controls for Atlas design §11. */

import type {
  ObservationColorVariable,
  ObservationShape,
  ObservationSizeRange,
  ObservationSizeVariable,
} from '../../atlas/observation-encoding';
import type { ExplorerState } from '../../atlas/url-state';
import { InfoTip } from './InfoTip';

interface ObservationControlsProps {
  disabled: boolean;
  state: ExplorerState;
  onColor: (value: ObservationColorVariable) => void;
  onHemisphereRange: (value: ObservationSizeRange) => void;
  onPointRange: (value: ObservationSizeRange) => void;
  onSamplingAreas: (visible: boolean) => void;
  onShape: (value: ObservationShape) => void;
  onSize: (value: ObservationSizeVariable) => void;
}

const SHAPES: readonly [ObservationShape, string][] = [
  ['circle', 'Circles'],
  ['hemisphere', 'Hemispheres'],
  ['pin', 'Pins'],
];
const COLORS: readonly [ObservationColorVariable, string][] = [
  ['white', 'White'],
  ['study', 'Study'],
  ['frequency', 'Observed frequency'],
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
  onHemisphereRange,
  onPointRange,
  onSamplingAreas,
  onShape,
  onSize,
}: ObservationControlsProps) {
  const range =
    state.observationShape === 'hemisphere'
      ? state.observationHemisphereRange
      : state.observationPointRange;
  const bounds = state.observationShape === 'hemisphere' ? [10, 500] : [4, 40];
  const units = state.observationShape === 'hemisphere' ? 'visual km' : 'px';
  const setRange = (value: ObservationSizeRange) =>
    state.observationShape === 'hemisphere'
      ? onHemisphereRange(value)
      : onPointRange(value);

  return (
    <div className="atlas-control-grid">
      <div className="atlas-field">
        <span className="atlas-field__title">
          <label htmlFor="atlas-marker-shape">Marker shape</label>
          <InfoTip label="marker shape">
            Three presentations of the same measured location. Hemispheres use a
            visual radius—not the study’s sampling radius.
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
            White is the default. Study is categorical; frequency and allele
            count use continuous scales from the loaded observations.
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
          <span>
            Min · {Math.round(range[0])} {units}
          </span>
          <input
            type="range"
            min={bounds[0]}
            max={bounds[1]}
            step="1"
            value={range[0]}
            disabled={disabled}
            onChange={(event) =>
              setRange([
                Math.min(Number(event.target.value), range[1]),
                range[1],
              ])
            }
          />
        </label>
        <label>
          <span>
            Max · {Math.round(range[1])} {units}
          </span>
          <input
            type="range"
            min={bounds[0]}
            max={bounds[1]}
            step="1"
            value={range[1]}
            disabled={disabled}
            onChange={(event) =>
              setRange([
                range[0],
                Math.max(Number(event.target.value), range[0]),
              ])
            }
          />
        </label>
      </div>

      <div className="atlas-check-row">
        <label htmlFor="atlas-sampling-areas">
          <input
            id="atlas-sampling-areas"
            type="checkbox"
            checked={state.samplingAreas}
            disabled={disabled}
            onChange={(event) => onSamplingAreas(event.target.checked)}
          />
          Sampling areas
        </label>
        <InfoTip label="sampling areas">
          Outlines the source-supported geographic precision. Very large rings
          mean the source located a sample only to a broad administrative area.
        </InfoTip>
      </div>
    </div>
  );
}
