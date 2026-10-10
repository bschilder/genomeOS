/**
 * Compact scientific legend and expandable explanation for Atlas design §11;
 * on phones a one-row strip [label | ramp | info] (mobile sheets design
 * 2026-10-07 §A.1.7) whose popover closes on Escape. On phones the popover
 * stays inside the explorer wherever the docked strip rides (above it, or
 * below over an open sheet, scrolling within the room it has), and a tap
 * outside it closes it.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from 'react';

import type { ArtifactRef } from '../../atlas/contracts';
import type { ExplorerState } from '../../atlas/url-state';
import {
  paletteStops,
  type Metric,
  type PaletteId,
} from '../../atlas/visual-encoding';
import { placeLegendPopover } from './sheet-layout';
import { useEscapeLayer } from './useEscapeStack';
import { MOBILE_QUERY, useMediaQuery } from './useMediaQuery';

interface AtlasLegendProps {
  artifact: ArtifactRef;
  state: ExplorerState;
  /** The scene's committed layer; the legend never runs ahead of the pixels. */
  layer?: { metric: Metric; palette: PaletteId } | null;
  /** True while a cold reveal is still adding chunks. */
  loading?: boolean;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`;
}

export function AtlasLegend({
  artifact,
  layer = null,
  loading = false,
  state,
}: AtlasLegendProps) {
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const isMobile = useMediaQuery(MOBILE_QUERY);
  // Escape returns focus to the summary only from the legend itself or from <body>: an
  // Escape pressed inside another layer (the catalog's search box) closes the popover
  // without pulling focus out of that layer. A tap outside never moves focus.
  const closeInfo = useCallback((restoreFocus: boolean) => {
    const focused = document.activeElement;
    const returnFocus =
      restoreFocus &&
      (!focused ||
        focused === document.body ||
        Boolean(details.current?.contains(focused)));
    if (details.current) details.current.open = false;
    setInfoOpen(false);
    if (returnFocus) summary.current?.focus();
  }, []);
  // The popover joins the stack from the summary's click, not from the async `toggle`
  // event: click is a discrete React event, so the layer is registered before `open` is
  // even set and an Escape pressed right after opening closes the popover, not the layer
  // under it (§A.1.9: the popover is innermost). `onToggle` keeps the state in sync, and
  // the close callback resets it because Chromium can merge two toggle events into one.
  useEscapeLayer(infoOpen, () => closeInfo(true), 'popover');
  const metric = layer?.metric ?? state.metric;
  const palette = layer?.palette ?? state.surfacePalette;

  // Phones: keep the open popover inside the explorer as the strip moves with the
  // sheets, and close it on a tap outside (which also starts any sheet drag).
  useLayoutEffect(() => {
    const element = details.current;
    if (!isMobile || !infoOpen || !element) return;
    const legend = element.closest('.atlas-legend');
    const explorer = element.closest('.atlas-explorer');
    // A short explorer hides the strip above peek; its popover goes with it.
    const place = () => {
      if (legend && getComputedStyle(legend).visibility === 'hidden')
        closeInfo(false);
      else placeLegendPopover(element);
    };
    place();
    // Not the popover itself: placing it resizes it, which would loop.
    const resize = new ResizeObserver(place);
    for (const node of [explorer, legend]) if (node) resize.observe(node);
    legend?.addEventListener('transitionend', place);
    return () => {
      resize.disconnect();
      legend?.removeEventListener('transitionend', place);
    };
  }, [closeInfo, infoOpen, isMobile]);
  useEffect(() => {
    if (!isMobile || !infoOpen) return;
    const dismiss = (event: PointerEvent) => {
      const target = event.target instanceof Node ? event.target : null;
      if (!details.current?.contains(target)) closeInfo(false);
    };
    document.addEventListener('pointerdown', dismiss, true);
    return () => document.removeEventListener('pointerdown', dismiss, true);
  }, [closeInfo, infoOpen, isMobile]);
  const domain = artifact.metric_domains[metric];
  const isEstimate = metric === 'post_mean';
  const metricLabel = isEstimate ? 'Modeled frequency' : 'Model uncertainty';
  const shortLabel = isEstimate ? 'Frequency' : 'Uncertainty';
  const low = percent(domain[0]);
  const high = percent(domain[1]);
  const colors = paletteStops(palette);
  const scaleStyle = {
    '--atlas-scale': `linear-gradient(90deg, ${colors.join(', ')})`,
  } as CSSProperties;
  const priorStyle = {
    '--atlas-prior-scale': `linear-gradient(90deg, ${colors.join(', ')})`,
  } as CSSProperties;
  return (
    <aside
      className="atlas-legend"
      aria-label="Map legend"
      data-atlas-legend-loading={loading ? 'true' : undefined}
    >
      <div className="atlas-legend__compact">
        <strong>
          <span className="atlas-legend__label-full">{metricLabel}</span>
          <span className="atlas-legend__label-short" aria-hidden="true">
            {shortLabel}
          </span>
        </strong>
        <div
          className="atlas-color-scale"
          role="img"
          aria-label={`${metricLabel} color scale, ${low} to ${high}`}
        >
          <span>{low}</span>
          <i aria-hidden="true" style={scaleStyle} />
          <span>{high}</span>
        </div>
        <span className="atlas-legend__mode">
          {state.view === 'map'
            ? '2D'
            : state.elevation
              ? 'Color + height'
              : 'Color'}
        </span>
        {loading && (
          <span
            className="atlas-legend__mode atlas-legend__loading"
            role="status"
          >
            Loading map…
          </span>
        )}
        <details
          className="atlas-legend__info"
          ref={details}
          onToggle={(event) => setInfoOpen(event.currentTarget.open)}
        >
          <summary
            aria-label="Explain the legend"
            ref={summary}
            onClick={() => setInfoOpen(!details.current?.open)}
          >
            i
          </summary>
          <div>
            <h2>
              {artifact.label}
              <span className="atlas-legend__heading-metric">
                {metricLabel}
              </span>
            </h2>
            <p>
              Color shows the modeled value. Dots mark estimates still driven
              mostly by the model’s starting assumptions because local evidence
              is limited; those cells are excluded from summaries. Neutral
              hatching means the value is unknown.
            </p>
            <div className="atlas-legend__keys">
              <span>
                <i className="atlas-key atlas-key--ring" /> Measurement
              </span>
              <span>
                <i className="atlas-key atlas-key--fill" /> Modeled surface
              </span>
              <span>
                <i className="atlas-key atlas-key--unknown" /> Unknown
              </span>
              <span>
                <i className="atlas-key atlas-key--prior" style={priorStyle} />{' '}
                Dots: mostly model assumptions
              </span>
            </div>
            <p className="atlas-legend__version">
              Model {artifact.model_version} · data {artifact.data_version} · H3
              resolution {artifact.resolution}
              {state.elevation &&
                state.view !== 'map' &&
                ` · height scale 0–${Math.round(180 * state.exaggeration)} km`}
            </p>
          </div>
        </details>
      </div>
    </aside>
  );
}
