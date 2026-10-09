/** Evidence-only pick inspector for Atlas design §11. */

import { cellToLatLng } from 'h3-js';
import { useLayoutEffect, useRef, type RefObject } from 'react';

import type {
  ArtifactRef,
  Observation,
  SurfaceCell,
} from '../../atlas/contracts';
import type { ObservationColorEncoding } from '../../atlas/observation-encoding';
import type { ObservationPlaceContext } from '../../atlas/place-context';
import type { SurfaceArtifact } from '../../atlas/surface-columns';
import { sitePath } from '../../lib/paths';
import {
  CELL_VALUES_UNAVAILABLE,
  LOADING_CELL_VALUES,
  RETRY_CELL_VALUES,
  surfaceCellView,
  valuesView,
  type DetailStatus,
  type SurfaceSelection,
} from './surface-cell-view';
import { useEscapeLayer } from './useEscapeStack';
import {
  useExplorerPanel,
  usePanelBodyId,
  usePanelBodyInert,
} from './useExplorerPanels';

export type InspectorSelection =
  | { kind: 'surface'; value: SurfaceCell }
  | SurfaceSelection
  | { kind: 'observation'; value: Observation };

interface InspectorPanelProps {
  artifact: ArtifactRef;
  colorEncoding?: ObservationColorEncoding | null;
  detail?: DetailStatus;
  placeContext?: ObservationPlaceContext | null;
  selection: InspectorSelection;
  surface?: SurfaceArtifact | null;
  onClose: () => void;
  onRetryDetail?: () => void;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export function evidenceSupportLabel(support: SurfaceCell['support']): string {
  if (support === 'prior_dominated')
    return 'Mostly model assumptions (limited local data)';
  return support.replace('_', ' ');
}

export function googleMapsUrl(latitude: number, longitude: number): string {
  const coordinates = `${latitude.toFixed(6)},${longitude.toFixed(6)}`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(coordinates)}`;
}

export function googleMapsPolygonUrl(h3Index: string): string {
  return sitePath(`/app/polygon/?cell=${encodeURIComponent(h3Index)}`);
}

function GoogleMapsIcon() {
  return (
    <svg
      className="atlas-centroid-link__icon"
      data-google-maps-icon
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M12 2a7 7 0 0 0-7 7c0 5.1 7 13 7 13s7-7.9 7-13a7 7 0 0 0-7-7Zm0 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/**
 * "Retry cell values" unmounts as soon as the retry moves the detail tier back
 * to loading. Its layout cleanup runs before React removes the button, so a
 * retry that still holds focus hands it to the panel's Close button, which
 * stays mounted in every cell-value state and sits outside the phone sheet's
 * inert body, instead of letting it fall to <body> (mobile sheets design
 * 2026-10-07 §A.1.6).
 */
function RetryCellValues({
  close,
  onRetry,
}: {
  close: RefObject<HTMLButtonElement | null>;
  onRetry: () => void;
}) {
  const button = useRef<HTMLButtonElement | null>(null);
  useLayoutEffect(() => {
    const node = button.current;
    return () => {
      if (node && node.ownerDocument.activeElement === node)
        close.current?.focus();
    };
  }, [close]);
  return (
    <button
      className="atlas-inspector__retry"
      ref={button}
      type="button"
      onClick={onRetry}
    >
      {RETRY_CELL_VALUES}
    </button>
  );
}

export function InspectorPanel({
  artifact,
  colorEncoding,
  detail = 'loading',
  placeContext,
  selection,
  surface = null,
  onClose,
  onRetryDetail,
}: InspectorPanelProps) {
  const view =
    selection.kind !== 'surface'
      ? null
      : 'value' in selection
        ? valuesView(selection.value)
        : surfaceCellView(surface, selection, detail);
  // A panel that renders nothing must not hold the Escape stack or the phone panel sheet.
  const shown = selection.kind !== 'surface' || view !== null;
  useEscapeLayer(shown, onClose, 'inspector');
  useExplorerPanel('inspector', shown, onClose);
  const bodyId = usePanelBodyId('inspector');
  const bodyInert = usePanelBodyInert();
  const close = useRef<HTMLButtonElement | null>(null);
  if (selection.kind === 'surface') {
    if (!view) return null;
    const [centroidLat, centroidLon] = cellToLatLng(view.h3Index);
    return (
      <aside className="atlas-inspector" aria-label="Selected map cell">
        <button
          className="atlas-inspector__close"
          data-sheet-peek
          ref={close}
          type="button"
          onClick={onClose}
          aria-label="Close inspector"
        >
          ×
        </button>
        <p className="atlas-kicker">Modeled estimate</p>
        <h2 data-sheet-peek>Inferred map cell</h2>
        <div
          className="atlas-panel-body"
          data-sheet-body
          id={bodyId}
          inert={bodyInert}
        >
          <dl>
            {view.state === 'values' ? (
              <>
                <div>
                  <dt>Posterior estimate</dt>
                  <dd>{percent(view.cell.post_mean)}</dd>
                </div>
                <div>
                  <dt>95% credible interval</dt>
                  <dd>
                    {percent(view.cell.q025)}–{percent(view.cell.q975)}
                  </dd>
                </div>
                <div>
                  <dt>Uncertainty</dt>
                  <dd>{percent(view.cell.post_sd)}</dd>
                </div>
              </>
            ) : (
              <div>
                <dt>Cell values</dt>
                <dd>
                  <span role="status">
                    {view.state === 'loading'
                      ? LOADING_CELL_VALUES
                      : CELL_VALUES_UNAVAILABLE}
                  </span>
                  {view.state === 'unavailable' && onRetryDetail && (
                    <RetryCellValues close={close} onRetry={onRetryDetail} />
                  )}
                </dd>
              </div>
            )}
            <div>
              <dt>Evidence support</dt>
              <dd>{evidenceSupportLabel(view.support)}</dd>
            </div>
            {view.state === 'values' && (
              <div>
                <dt>Nearest measurement</dt>
                <dd>{Math.round(view.cell.dist_nearest_obs_km)} km</dd>
              </div>
            )}
            <div>
              <dt>Cell ID</dt>
              <dd>{view.h3Index}</dd>
            </div>
            <div>
              <dt>Google Maps</dt>
              <dd>
                <details className="atlas-map-options">
                  <summary
                    aria-label="Choose how to open this cell in Google Maps"
                    className="atlas-map-options__trigger"
                    role="button"
                  >
                    <GoogleMapsIcon />
                    <span className="atlas-centroid-link__coordinates">
                      <span>{centroidLon.toFixed(4)}° lon</span>
                      <span>{centroidLat.toFixed(4)}° lat</span>
                    </span>
                  </summary>
                  <div className="atlas-map-options__menu">
                    <a
                      href={googleMapsUrl(centroidLat, centroidLon)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <strong>Centroid</strong>
                      <span className="atlas-centroid-link__coordinates">
                        <span>{centroidLon.toFixed(4)}° lon</span>
                        <span>{centroidLat.toFixed(4)}° lat</span>
                      </span>
                    </a>
                    <a
                      href={googleMapsPolygonUrl(view.h3Index)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <strong>Polygon</strong>
                      <span>Draw the full modeled cell boundary</span>
                    </a>
                  </div>
                </details>
              </dd>
            </div>
          </dl>
          <p className="atlas-inspector__meta">
            Model {artifact.model_version}; data {artifact.data_version};
            registry {artifact.registry_version}.
          </p>
        </div>
      </aside>
    );
  }

  const observation = selection.value;
  const encodedValue =
    colorEncoding?.label === 'Observed frequency' &&
    typeof colorEncoding.value === 'number'
      ? percent(colorEncoding.value)
      : typeof colorEncoding?.value === 'number'
        ? colorEncoding.value.toLocaleString()
        : colorEncoding?.value;
  return (
    <aside className="atlas-inspector" aria-label="Selected observation">
      <button
        className="atlas-inspector__close"
        data-sheet-peek
        type="button"
        onClick={onClose}
        aria-label="Close inspector"
      >
        ×
      </button>
      <p className="atlas-kicker">Measured observation</p>
      <h2 data-sheet-peek>{observation.population_label}</h2>
      <div
        className="atlas-panel-body"
        data-sheet-body
        id={bodyId}
        inert={bodyInert}
      >
        {placeContext && (
          <p
            className="atlas-inspector__place"
            title={`Nearby mapped place · ${placeContext.revision}`}
          >
            <span>Nearby place</span>
            <strong>
              {placeContext.name}
              {placeContext.region ? ` · ${placeContext.region}` : ''}
            </strong>
          </p>
        )}
        {colorEncoding?.label && (
          <div className="atlas-observation-color-key">
            <span
              className="atlas-observation-color-key__swatch"
              data-observation-color={colorEncoding.color}
              style={{ backgroundColor: colorEncoding.color }}
            />
            <span>{colorEncoding.label}</span>
            <strong>{encodedValue}</strong>
          </div>
        )}
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
      </div>
    </aside>
  );
}
