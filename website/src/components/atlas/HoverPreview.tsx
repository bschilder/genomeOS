/** Compact evidence preview for Atlas design §11. */

import type { CSSProperties } from 'react';

import type { ObservationColorEncoding } from '../../atlas/observation-encoding';
import type { ObservationPlaceContext } from '../../atlas/place-context';
import {
  evidenceSupportLabel,
  type InspectorSelection,
} from './InspectorPanel';

interface HoverPreviewProps {
  colorEncoding?: ObservationColorEncoding | null;
  placeContext?: ObservationPlaceContext | null;
  position: { x: number; y: number };
  selection: InspectorSelection;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function encodedValue(encoding: ObservationColorEncoding): string {
  if (
    encoding.label === 'Observed frequency' &&
    typeof encoding.value === 'number'
  )
    return percent(encoding.value);
  if (typeof encoding.value === 'number')
    return encoding.value.toLocaleString();
  return encoding.value ?? '';
}

export function HoverPreview({
  colorEncoding,
  placeContext,
  position,
  selection,
}: HoverPreviewProps) {
  const style = {
    '--atlas-hover-x': `${position.x}px`,
    '--atlas-hover-y': `${position.y}px`,
  } as CSSProperties;

  if (selection.kind === 'surface') {
    const cell = selection.value;
    return (
      <div className="atlas-hover-preview" style={style} aria-hidden="true">
        <span>Modeled estimate</span>
        <dl>
          <div>
            <dt>Posterior</dt>
            <dd>{percent(cell.post_mean)}</dd>
          </div>
          <div>
            <dt>95% credible range</dt>
            <dd>
              {percent(cell.q025)}–{percent(cell.q975)}
            </dd>
          </div>
          <div>
            <dt>Uncertainty</dt>
            <dd>{percent(cell.post_sd)}</dd>
          </div>
        </dl>
        <small>{evidenceSupportLabel(cell.support)}</small>
      </div>
    );
  }

  const observation = selection.value;
  return (
    <div className="atlas-hover-preview" style={style} aria-hidden="true">
      <span>Measured observation</span>
      <strong>{observation.population_label}</strong>
      {placeContext && (
        <small
          className="atlas-observation-place"
          title={`Nearby mapped place · ${placeContext.revision}`}
        >
          {placeContext.name}
          {placeContext.region ? ` · ${placeContext.region}` : ''}
        </small>
      )}
      {colorEncoding?.label && (
        <div className="atlas-observation-color-key">
          <span
            className="atlas-observation-color-key__swatch"
            data-observation-color={colorEncoding.color}
            style={{ backgroundColor: colorEncoding.color }}
          />
          <span>{colorEncoding.label}</span>
          <strong>{encodedValue(colorEncoding)}</strong>
        </div>
      )}
      <dl>
        <div>
          <dt>Measured frequency</dt>
          <dd>{percent(observation.ac / observation.an)}</dd>
        </div>
        <div>
          <dt>Allele count</dt>
          <dd>
            {observation.ac}/{observation.an}
          </dd>
        </div>
        <div>
          <dt>Sampling radius</dt>
          <dd>{observation.radius_km.toFixed(1)} km</dd>
        </div>
      </dl>
    </div>
  );
}
