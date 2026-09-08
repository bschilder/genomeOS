/** Hover and persistent-selection highlights for Atlas design §11. */

import {
  Cartesian3,
  Color,
  Material,
  PointPrimitive,
  PointPrimitiveCollection,
  Polyline,
  PolylineCollection,
  PrimitiveCollection,
  type Scene,
} from 'cesium';

import type {
  Observation,
  ObservationArtifact,
  SurfaceArtifact,
  SurfaceCell,
} from '../contracts';
import { heightForCell, type Metric } from '../visual-encoding';
import type { AtlasPick } from './types';
import { surfaceHeightAt } from './observation-layer';
import { h3BoundaryDegrees } from './surface-layer';

export type HighlightKind = 'hover' | 'selection';

export interface HighlightStyle {
  color: string;
  pointSize: number;
  width: number;
}

interface HighlightEntry {
  baseColor: Color;
  line: Polyline;
  lineMaterial: Material;
  point: PointPrimitive;
}

const HOVER_DURATION_MS = 160;
const SURFACE_CLEARANCE_METRES = 5_500;

export function highlightStyle(kind: HighlightKind): HighlightStyle {
  return kind === 'hover'
    ? { color: '#b9f8ff', pointSize: 26, width: 4 }
    : { color: '#ffd56a', pointSize: 32, width: 5 };
}

function createEntry(
  kind: HighlightKind,
  lines: PolylineCollection,
  points: PointPrimitiveCollection,
): HighlightEntry {
  const style = highlightStyle(kind);
  const baseColor = Color.fromCssColorString(style.color);
  const lineMaterial = Material.fromType('PolylineGlow', {
    color: baseColor.withAlpha(0),
    glowPower: kind === 'hover' ? 0.32 : 0.18,
    taperPower: 0.6,
  });
  const line = lines.add({
    loop: true,
    material: lineMaterial,
    positions: Cartesian3.fromDegreesArray([0, 0, 0.1, 0]),
    show: false,
    width: style.width,
  });
  const point = points.add({
    color: baseColor.withAlpha(0.12),
    disableDepthTestDistance: 0,
    outlineColor: baseColor.withAlpha(0),
    outlineWidth: kind === 'hover' ? 5 : 6,
    pixelSize: style.pointSize,
    position: Cartesian3.fromDegrees(0, 0),
    show: false,
  });
  return { baseColor, line, lineMaterial, point };
}

function setEntryOpacity(
  entry: HighlightEntry,
  opacity: number,
  earthOpacity = 1,
): void {
  const lineColor = entry.lineMaterial.uniforms.color;
  if (lineColor instanceof Color) lineColor.alpha = opacity * earthOpacity;
  entry.point.color.alpha = 0.12 * opacity * earthOpacity;
  entry.point.outlineColor.alpha = opacity * earthOpacity;
}

export class HighlightLayer {
  readonly collection = new PrimitiveCollection();
  readonly #scene: Scene;
  readonly #hover: HighlightEntry;
  readonly #selection: HighlightEntry;
  #surface: SurfaceArtifact | null = null;
  #observations = new Map<string, Observation>();
  #surfaceCells = new Map<string, SurfaceCell>();
  #metric: Metric = 'post_mean';
  #elevation = false;
  #exaggeration = 1;
  #earthOpacity = 1;
  #hoverPick: AtlasPick | null = null;
  #selectionPick: AtlasPick | null = null;
  #hoverSequence = 0;

  constructor(scene: Scene) {
    this.#scene = scene;
    const lines = new PolylineCollection();
    const points = new PointPrimitiveCollection();
    this.collection.add(lines);
    this.collection.add(points);
    this.#hover = createEntry('hover', lines, points);
    this.#selection = createEntry('selection', lines, points);
  }

  setArtifacts(
    surface: SurfaceArtifact,
    observations: ObservationArtifact | null,
    metric: Metric,
    elevation: boolean,
    exaggeration: number,
  ): void {
    this.#surface = surface;
    this.#surfaceCells = new Map(
      surface.cells.map((cell) => [cell.h3_index, cell]),
    );
    this.#observations = new Map(
      (observations?.observations ?? []).map((observation) => [
        observation.source_record_id,
        observation,
      ]),
    );
    this.#metric = metric;
    this.#elevation = elevation;
    this.#exaggeration = exaggeration;
    this.#show(this.#hover, this.#hoverPick);
    this.#show(this.#selection, this.#selectionPick);
  }

  setElevationStyle(enabled: boolean, exaggeration: number): void {
    this.#elevation = enabled;
    this.#exaggeration = exaggeration;
    this.#show(this.#hover, this.#hoverPick);
    this.#show(this.#selection, this.#selectionPick);
  }

  setHover(pick: AtlasPick | null, reducedMotion: boolean): void {
    this.#hoverPick = pick;
    const sequence = ++this.#hoverSequence;
    if (pick) this.#show(this.#hover, pick);
    const target = pick ? 1 : 0;
    if (reducedMotion) {
      setEntryOpacity(this.#hover, target, this.#earthOpacity);
      if (!pick) this.#hide(this.#hover);
      this.#scene.requestRender();
      return;
    }
    const started = performance.now();
    const frame = (now: number) => {
      if (sequence !== this.#hoverSequence) return;
      const linear = Math.min(1, (now - started) / HOVER_DURATION_MS);
      const eased = linear * linear * (3 - 2 * linear);
      setEntryOpacity(
        this.#hover,
        pick ? eased : 1 - eased,
        this.#earthOpacity,
      );
      this.#scene.requestRender();
      if (linear < 1) requestAnimationFrame(frame);
      else if (!pick) this.#hide(this.#hover);
    };
    requestAnimationFrame(frame);
  }

  setSelection(pick: AtlasPick | null): void {
    this.#selectionPick = pick;
    this.#show(this.#selection, pick);
    setEntryOpacity(this.#selection, pick ? 1 : 0, this.#earthOpacity);
    this.#scene.requestRender();
  }

  setEarthOpacity(opacity: number): void {
    this.#earthOpacity = Math.min(1, Math.max(0.15, opacity));
    setEntryOpacity(this.#hover, this.#hoverPick ? 1 : 0, this.#earthOpacity);
    setEntryOpacity(
      this.#selection,
      this.#selectionPick ? 1 : 0,
      this.#earthOpacity,
    );
    this.#scene.requestRender();
  }

  #hide(entry: HighlightEntry): void {
    entry.line.show = false;
    entry.point.show = false;
  }

  #show(entry: HighlightEntry, pick: AtlasPick | null): void {
    if (!pick || !this.#surface) {
      this.#hide(entry);
      return;
    }
    if (pick.kind === 'surface') {
      const cell = this.#surfaceCells.get(pick.h3Index);
      if (!cell) {
        this.#hide(entry);
        return;
      }
      const top = this.#elevation
        ? heightForCell(
            cell,
            this.#surface.artifact.metric_domains[this.#metric],
            this.#exaggeration,
            this.#metric,
          )
        : 0;
      const coordinates = h3BoundaryDegrees(pick.h3Index).flatMap(
        ([lon, lat]) => [lon, lat, top + SURFACE_CLEARANCE_METRES],
      );
      entry.line.positions = Cartesian3.fromDegreesArrayHeights(coordinates);
      entry.line.show = true;
      entry.point.show = false;
      return;
    }
    const observation = this.#observations.get(pick.sourceRecordId);
    if (!observation) {
      this.#hide(entry);
      return;
    }
    const top = surfaceHeightAt(
      observation,
      this.#surface,
      this.#metric,
      this.#elevation,
      this.#exaggeration,
      this.#surfaceCells,
    );
    entry.point.position = Cartesian3.fromDegrees(
      observation.lon,
      observation.lat,
      top + SURFACE_CLEARANCE_METRES,
    );
    entry.point.show = true;
    entry.line.show = false;
  }
}
