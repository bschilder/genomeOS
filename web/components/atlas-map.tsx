"use client";

/** MapLibre + deck.gl Atlas client with independent evidence layers (design §11). */

import type {PickingInfo} from "@deck.gl/core";
import {PolygonLayer, ScatterplotLayer} from "@deck.gl/layers";
import {MapboxOverlay} from "@deck.gl/mapbox";
import * as maplibregl from "maplibre-gl";
import type {StyleSpecification} from "maplibre-gl";
import {useEffect, useMemo, useRef, useState} from "react";
import {
  fetchObservations,
  fetchSurface,
  fetchVariants,
  resolutionForZoom,
  viewportSegments,
  type Bounds,
  type Observation,
  type SurfaceCell,
  type Variant,
} from "../lib/atlas";

type Metric = "post_mean" | "post_sd";
type Viewport = Bounds & {zoom: number};
type Color = [number, number, number, number];

const INITIAL_VIEWPORT: Viewport = {west: -180, south: -85, east: 180, north: 85, zoom: 1.2};
function mapStyle(countries: object): StyleSpecification {
  return {
    version: 8,
    name: "GenomeOS Natural Earth",
    sources: {
      countries: {
        type: "geojson",
        data: countries as never,
        attribution: "Natural Earth",
      },
    },
    layers: [
      {id: "ocean", type: "background", paint: {"background-color": "#edf3f8"}},
      {
        id: "countries",
        type: "fill",
        source: "countries",
        paint: {"fill-color": "#f8fafc", "fill-opacity": 0.94},
      },
      {
        id: "country-borders",
        type: "line",
        source: "countries",
        paint: {"line-color": "#91a0b2", "line-width": 0.7},
      },
    ],
  };
}

export function AtlasMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [variantId, setVariantId] = useState("");
  const [viewport, setViewport] = useState<Viewport>(INITIAL_VIEWPORT);
  const [cells, setCells] = useState<SurfaceCell[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [metric, setMetric] = useState<Metric>("post_mean");
  const [showSurface, setShowSurface] = useState(true);
  const [showMask, setShowMask] = useState(true);
  const [showObservations, setShowObservations] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [versions, setVersions] = useState({data: "", model: ""});

  const selected = variants.find((variant) => variant.variant_id === variantId);
  const resolution = selected ? resolutionForZoom(selected.resolutions, viewport.zoom) : null;
  const supported = cells.filter((cell) => !isMasked(cell));
  const masked = cells.filter(isMasked);
  const range = useMemo(() => valueRange(supported, metric), [supported, metric]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let disposed = false;
    let map: maplibregl.Map | null = null;
    const initialize = async () => {
      const response = await fetch("/preview/basemap");
      if (!response.ok) throw new Error("The packaged basemap is unavailable.");
      const countries = await response.json() as object;
      if (disposed || !containerRef.current) return;
      map = new maplibregl.Map({
        container: containerRef.current,
        style: mapStyle(countries),
        center: [10, 16],
        zoom: INITIAL_VIEWPORT.zoom,
        minZoom: 0.8,
        maxZoom: 10,
        renderWorldCopies: false,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), "top-right");
      map.addControl(new maplibregl.FullscreenControl(), "top-right");
      map.addControl(new maplibregl.AttributionControl({compact: true}), "bottom-right");
      const overlay = new MapboxOverlay({interleaved: false, layers: []});
      map.addControl(overlay);
      const updateViewport = () => {
        if (!map) return;
        const bounds = map.getBounds();
        setViewport({
          west: bounds.getWest(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          north: bounds.getNorth(),
          zoom: map.getZoom(),
        });
      };
      setMapReady(true);
      updateViewport();
      map.on("load", updateViewport);
      map.on("moveend", updateViewport);
      mapRef.current = map;
      overlayRef.current = overlay;
    };
    void initialize().catch((cause: Error) => setError(cause.message));
    return () => {
      disposed = true;
      overlayRef.current = null;
      mapRef.current = null;
      map?.remove();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchVariants(controller.signal)
      .then((response) => {
        setVariants(response.items);
        const requested = new URLSearchParams(window.location.search).get("variant");
        const initial = response.items.find((item) => item.variant_id === requested) ?? response.items[0];
        if (!initial) throw new Error("This artifact catalog contains no variants.");
        setVariantId(initial.variant_id);
      })
      .catch((cause: Error) => {
        if (cause.name !== "AbortError") setError(cause.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!mapReady || !selected || resolution === null) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const segments = viewportSegments(viewport, viewport.zoom);
    fetchSurface(selected.variant_id, resolution, segments, controller.signal)
      .then((response) => {
        setCells(response.items);
        setVersions({data: response.data_version, model: response.model_version});
        setLoading(false);
      })
      .catch((cause: Error) => {
        if (cause.name !== "AbortError") {
          setError(cause.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [mapReady, resolution, selected?.variant_id, viewport]);

  useEffect(() => {
    if (!selected?.has_observations) {
      setObservations([]);
      setShowObservations(false);
      return;
    }
    setShowObservations(true);
    const controller = new AbortController();
    fetchObservations(selected.variant_id, controller.signal)
      .then((response) => setObservations(response.items))
      .catch((cause: Error) => {
        if (cause.name !== "AbortError") setError(cause.message);
      });
    return () => controller.abort();
  }, [selected?.has_observations, selected?.variant_id]);

  useEffect(() => {
    if (!overlayRef.current) return;
    const layers = [
      new PolygonLayer<SurfaceCell>({
        id: "inferred-surface",
        data: supported,
        visible: showSurface,
        pickable: true,
        filled: true,
        stroked: true,
        getPolygon: (cell) => cell.boundary ?? [],
        getFillColor: (cell) => ramp(normalize(cell[metric], range)),
        getLineColor: [255, 255, 255, 70],
        lineWidthMinPixels: 0.35,
        opacity: 0.82,
      }),
      new PolygonLayer<SurfaceCell>({
        id: "data-support-mask",
        data: masked,
        visible: showMask,
        pickable: true,
        filled: true,
        stroked: true,
        getPolygon: (cell) => cell.boundary ?? [],
        getFillColor: (cell) =>
          cell.support === "unknown" ? [190, 199, 211, 190] : [112, 124, 143, 205],
        getLineColor: [76, 88, 107, 180],
        lineWidthMinPixels: 0.45,
      }),
      new ScatterplotLayer<Observation>({
        id: "measured-observations",
        data: observations,
        visible: showObservations && Boolean(selected?.has_observations),
        pickable: true,
        radiusUnits: "meters",
        radiusMinPixels: 4,
        radiusMaxPixels: 45,
        getPosition: (point) => [point.lon, point.lat],
        getRadius: (point) => Math.max(2_500, point.radius_km * 1_000),
        getFillColor: (point) => [0, 202, 211, Math.min(235, 75 + Math.log10(point.an + 1) * 38)],
        getLineColor: [255, 255, 255, 240],
        stroked: true,
        lineWidthMinPixels: 1.5,
      }),
    ];
    overlayRef.current.setProps({layers, getTooltip: tooltipFor});
  }, [masked, metric, observations, range, selected?.has_observations, showMask, showObservations, showSurface, supported]);

  useEffect(() => {
    if (!variantId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("variant", variantId);
    window.history.replaceState(null, "", url);
  }, [variantId]);

  const supportCounts = countSupport(cells);
  const unavailableObservations = !selected?.has_observations;

  return (
    <main className="atlas-shell">
      <header className="topbar">
        <div>
          <h1>GenomeOS Atlas</h1>
          <p>Explore published genomic evidence worldwide</p>
        </div>
        <div className="readiness"><span className="ready-dot" /> {loading ? "loading" : error ? "degraded" : "ready"}</div>
      </header>
      <section className="map-stage">
        <div ref={containerRef} className="map" aria-label="Interactive worldwide genomic evidence map" />
        <aside className="control-panel">
          <label className="eyebrow" htmlFor="variant">Disease or variant</label>
          <select id="variant" value={variantId} onChange={(event) => setVariantId(event.target.value)}>
            {variants.map((variant) => <option key={variant.variant_id} value={variant.variant_id}>{variant.label}</option>)}
          </select>

          <fieldset>
            <legend>Evidence layers</legend>
            <LayerToggle checked={showSurface} onChange={setShowSurface} color="#59409b" label="Inferred surface" />
            <LayerToggle checked={showMask} onChange={setShowMask} color="#bec7d3" label="Data-support mask" />
            <LayerToggle checked={showObservations} onChange={setShowObservations} color="#00cad3"
              label="Measured observations" disabled={unavailableObservations} />
            {unavailableObservations && <p className="availability">Not included in this published catalog</p>}
            <LayerToggle checked={false} onChange={() => undefined} color="#ee9b42" label="Burden" disabled />
            <p className="availability">Awaiting validated P3 artifacts</p>
          </fieldset>

          <fieldset>
            <legend>Surface color</legend>
            <div className="segmented">
              <button className={metric === "post_mean" ? "active" : ""} onClick={() => setMetric("post_mean")}>Frequency</button>
              <button className={metric === "post_sd" ? "active" : ""} onClick={() => setMetric("post_sd")}>Uncertainty</button>
            </div>
          </fieldset>

          <div className="surface-status">
            <span className="eyebrow">Visible data</span>
            <strong>{cells.length.toLocaleString()} H3 cells</strong>
            <span>resolution {resolution ?? "—"} · zoom {viewport.zoom.toFixed(1)}</span>
            <span>{supportCounts.observed ?? 0} observed-support · {supportCounts.interpolated ?? 0} interpolated</span>
            <span>{supportCounts.unknown ?? 0} unknown · {supportCounts.prior_dominated ?? 0} prior-dominated</span>
          </div>
          {error && <p className="error">{error}</p>}
          <p className="explanation">Surface estimates and measured observations remain separate layers. Grey cells are explicit refusals, not zero frequency. Zoom never creates scientific detail absent from the published artifact.</p>
        </aside>

        <div className="map-legend">
          <span>{range[0].toFixed(3)}</span><div className="legend-gradient" /><span>{range[1].toFixed(3)}</span>
          <strong>{metric === "post_mean" ? selected?.measurement.replaceAll("_", " ") : "posterior SD"}</strong>
        </div>
        <div className="version-chip">data {versions.data || "—"} · model {versions.model || "—"}</div>
      </section>
    </main>
  );
}

function LayerToggle({checked, onChange, color, label, disabled = false}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  color: string;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label className={`layer-toggle ${disabled ? "disabled" : ""}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span className="swatch" style={{background: color}} />
      <span>{label}</span>
    </label>
  );
}

function isMasked(cell: SurfaceCell): boolean {
  return cell.support === "unknown" || cell.support === "prior_dominated";
}

function valueRange(cells: SurfaceCell[], metric: Metric): [number, number] {
  if (!cells.length) return [0, 1];
  const values = cells.map((cell) => cell[metric]);
  return [Math.min(...values), Math.max(...values)];
}

function normalize(value: number, [minimum, maximum]: [number, number]): number {
  return maximum === minimum ? 0.5 : (value - minimum) / (maximum - minimum);
}

function ramp(value: number): Color {
  const stops: Color[] = [
    [48, 18, 59, 235], [65, 69, 171, 235], [42, 157, 143, 235],
    [168, 219, 52, 235], [249, 199, 79, 235], [215, 25, 28, 235],
  ];
  const scaled = Math.max(0, Math.min(0.999, value)) * (stops.length - 1);
  const index = Math.floor(scaled);
  const fraction = scaled - index;
  return stops[index].map((channel, position) =>
    Math.round(channel + (stops[index + 1][position] - channel) * fraction),
  ) as Color;
}

function countSupport(cells: SurfaceCell[]): Partial<Record<SurfaceCell["support"], number>> {
  return cells.reduce<Partial<Record<SurfaceCell["support"], number>>>((counts, cell) => {
    counts[cell.support] = (counts[cell.support] ?? 0) + 1;
    return counts;
  }, {});
}

function tooltipFor(info: PickingInfo): string | null {
  if (!info.object) return null;
  if (info.layer?.id === "measured-observations") {
    const point = info.object as Observation;
    return `${point.population_id}\nmeasured ${point.ac}/${point.an} alleles\nsource: ${point.source}`;
  }
  const cell = info.object as SurfaceCell;
  return `${cell.support}\nmean ${cell.post_mean.toFixed(4)}\n95% interval ${cell.q025.toFixed(4)}–${cell.q975.toFixed(4)}`;
}
