/** Measured-observation symbols and source-supported footprints for Atlas design §11. */

import { latLngToCell } from 'h3-js';
import {
  BillboardCollection,
  Cartesian3,
  Color,
  Material,
  PointPrimitiveCollection,
  PolylineCollection,
  PrimitiveCollection,
  VerticalOrigin,
} from 'cesium';

import type {
  Observation,
  ObservationArtifact,
  SurfaceArtifact,
  SurfaceCell,
} from '../contracts';
import {
  observationColor,
  observationDomains,
  observationSize,
  validateObservationSizeRange,
  type ObservationColorVariable,
  type ObservationShape,
  type ObservationSizeRange,
  type ObservationSizeVariable,
} from '../observation-encoding';
import type { SurfaceGeometry } from '../url-state';
import { heightForCell, type Metric } from '../visual-encoding';
import {
  litStudImage,
  observationSurfaceAnchor,
  observationSurfaceContext,
  observationSurfacePlacement,
  STUD_ASPECT_RATIO,
  type ObservationSurfaceAnchor,
} from './observation-symbols';

export type ObservationPick = { kind: 'observation'; sourceRecordId: string };

export interface ObservationLayerOptions {
  colorVariable: ObservationColorVariable;
  elevation: boolean;
  exaggeration: number;
  gradient: readonly [string, string, string];
  metric: Metric;
  opacity: number;
  samplingAreaColor: string;
  sizeRange: ObservationSizeRange;
  samplingAreas: boolean;
  shape: ObservationShape;
  sizeVariable: ObservationSizeVariable;
  solidColor: string;
  surface: SurfaceArtifact;
  surfaceGeometry: SurfaceGeometry;
}

export interface ObservationPrimitiveGroup {
  collection: PrimitiveCollection;
  isReady(): boolean;
  readyCount(): number;
  totalCount(): number;
  setElevationFactor(factor: number, force?: boolean): void;
  setEarthOpacity(opacity: number): void;
  setOpacity(opacity: number): void;
  setSamplingAreaColor(color: string): void;
  setSizeRange(range: ObservationSizeRange): void;
  setStyleOpacity(opacity: number): void;
  setVisibility(symbols: boolean, samplingAreas: boolean): void;
}

interface GeographicPoint {
  lat: number;
  lon: number;
}

interface SymbolEncoding {
  anchor: ObservationSurfaceAnchor;
  color: string;
  observation: Observation;
  size: number;
  sizePosition: number;
}

interface RingSample {
  baseHeight: number;
  latRadians: number;
  lonRadians: number;
}

const EARTH_RADIUS_KM = 6_371.0088;
const RING_CLEARANCE_METRES = 4_000;
const PIN_ASPECT_RATIO = 1.45;
const LIT_PIN_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" width="96" height="128" viewBox="0 0 96 128">
    <defs>
      <radialGradient id="pin" cx="34%" cy="24%" r="76%">
        <stop offset="0" stop-color="white"/>
        <stop offset="0.42" stop-color="#e5edf7"/>
        <stop offset="0.78" stop-color="#8090a5"/>
        <stop offset="1" stop-color="#152238"/>
      </radialGradient>
    </defs>
    <ellipse cx="48" cy="121" rx="13" ry="4" fill="#020712" fill-opacity=".35"/>
    <path d="M48 124C41 108 12 82 12 50C12 23 28 8 48 8S84 23 84 50C84 82 55 108 48 124Z" fill="url(#pin)" stroke="white" stroke-opacity=".52" stroke-width="3"/>
    <ellipse cx="36" cy="31" rx="10" ry="7" fill="white" fill-opacity=".34"/>
  </svg>
`)}`;

function litPinImage(): HTMLCanvasElement | string {
  if (typeof document === 'undefined') return LIT_PIN_IMAGE;
  const canvas = document.createElement('canvas');
  canvas.width = 96;
  canvas.height = 128;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas rendering is required for pins.');

  context.fillStyle = 'rgba(2, 7, 18, 0.35)';
  context.beginPath();
  context.ellipse(48, 121, 13, 4, 0, 0, Math.PI * 2);
  context.fill();

  context.beginPath();
  context.moveTo(48, 124);
  context.bezierCurveTo(41, 108, 12, 82, 12, 50);
  context.bezierCurveTo(12, 23, 28, 8, 48, 8);
  context.bezierCurveTo(68, 8, 84, 23, 84, 50);
  context.bezierCurveTo(84, 82, 55, 108, 48, 124);
  context.closePath();
  const body = context.createRadialGradient(33, 28, 2, 48, 52, 55);
  body.addColorStop(0, 'rgba(255, 255, 255, 1)');
  body.addColorStop(0.42, 'rgba(229, 237, 247, 1)');
  body.addColorStop(0.78, 'rgba(128, 144, 165, 1)');
  body.addColorStop(1, 'rgba(21, 34, 56, 1)');
  context.fillStyle = body;
  context.fill();
  context.strokeStyle = 'rgba(255, 255, 255, 0.52)';
  context.lineWidth = 3;
  context.stroke();

  context.fillStyle = 'rgba(255, 255, 255, 0.34)';
  context.beginPath();
  context.ellipse(36, 31, 10, 7, -0.25, 0, Math.PI * 2);
  context.fill();
  return canvas;
}

export function observationPickId(sourceRecordId: string): ObservationPick {
  return { kind: 'observation', sourceRecordId };
}

function samplingAreaMaterial(cssColor: string): Material {
  return Material.fromType('Color', {
    color: Color.fromCssColorString(cssColor).withAlpha(0.9),
  });
}

function surfaceCellMap(surface: SurfaceArtifact): Map<string, SurfaceCell> {
  return new Map(surface.cells.map((cell) => [cell.h3_index, cell]));
}

export function surfaceHeightAt(
  point: GeographicPoint,
  surface: SurfaceArtifact,
  metric: Metric,
  elevation: boolean,
  exaggeration: number,
  cells = surfaceCellMap(surface),
): number {
  if (!elevation) return 0;
  const h3Index = latLngToCell(
    point.lat,
    point.lon,
    surface.artifact.resolution,
  );
  const cell = cells.get(h3Index);
  if (!cell) return 0;
  return heightForCell(
    cell,
    surface.artifact.metric_domains[metric],
    exaggeration,
    metric,
  );
}

export function samplingRingSamples(
  observation: Observation,
  baseHeightAt: (point: GeographicPoint) => number,
  segments = 48,
): RingSample[] {
  const baseHeight = baseHeightAt(observation);
  const angularDistance = observation.radius_km / EARTH_RADIUS_KM;
  const lat1 = (observation.lat * Math.PI) / 180;
  const lon1 = (observation.lon * Math.PI) / 180;
  return Array.from({ length: segments }, (_, index) => {
    const bearing = (index / segments) * Math.PI * 2;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(angularDistance) +
        Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing),
    );
    const lon2 =
      lon1 +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
        Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2),
      );
    return {
      baseHeight,
      latRadians: lat2,
      lonRadians: lon2,
    };
  });
}

function ringPositions(
  samples: readonly RingSample[],
  elevationFactor: number,
): Cartesian3[] {
  return samples.map((sample) =>
    Cartesian3.fromRadians(
      sample.lonRadians,
      sample.latRadians,
      sample.baseHeight * elevationFactor + RING_CLEARANCE_METRES,
    ),
  );
}

function encodings(
  artifact: ObservationArtifact,
  options: ObservationLayerOptions,
): SymbolEncoding[] {
  const domains = observationDomains(artifact.observations);
  const range = options.sizeRange;
  validateObservationSizeRange(options.shape, range);
  const sizeDomain =
    options.sizeVariable === 'fixed'
      ? ([0, 1] as const)
      : domains[options.sizeVariable];
  const colorDomain =
    options.colorVariable === 'gradient'
      ? domains.frequency
      : options.colorVariable === 'ac'
        ? domains.ac
        : ([0, 1] as const);
  const context = observationSurfaceContext(
    options.surface,
    options.metric,
    options.surfaceGeometry,
  );
  return artifact.observations.map((observation) => {
    const sizePosition = observationSize(
      observation,
      options.sizeVariable,
      [0, 1],
      sizeDomain,
    );
    return {
      anchor: observationSurfaceAnchor(
        observation,
        options.surface,
        options.metric,
        options.surfaceGeometry,
        context,
      ),
      color: observationColor(
        observation,
        options.colorVariable,
        colorDomain,
        options.solidColor,
        options.gradient,
      ),
      observation,
      size: range[0] + sizePosition * (range[1] - range[0]),
      sizePosition,
    };
  });
}

export function buildObservationLayer(
  artifact: ObservationArtifact,
  options: ObservationLayerOptions,
): ObservationPrimitiveGroup {
  const collection = new PrimitiveCollection();
  const rings = new PolylineCollection();
  const points = new PointPrimitiveCollection();
  const pins = new BillboardCollection();
  const hemispheres = new BillboardCollection();
  const symbols = encodings(artifact, options);
  const cells = surfaceCellMap(options.surface);
  const baseHeightAt = (point: GeographicPoint) =>
    surfaceHeightAt(point, options.surface, options.metric, true, 1, cells);
  let elevationFactor = options.elevation ? options.exaggeration : 0;
  let lastElevationUpdate = Number.NEGATIVE_INFINITY;
  let fadeOpacity = 1;
  let earthOpacity = 1;
  let styleOpacity = options.opacity;
  const uploadColor = new Color();
  const ringSamples: RingSample[][] = [];
  const ringBaseColors: Color[] = [];
  for (const observation of artifact.observations) {
    const material = samplingAreaMaterial(options.samplingAreaColor);
    const color = material.uniforms.color as Color;
    ringBaseColors.push(color.clone());
    const samples = samplingRingSamples(observation, baseHeightAt);
    ringSamples.push(samples);
    rings.add({
      id: observationPickId(observation.source_record_id),
      loop: true,
      material,
      positions: ringPositions(samples, elevationFactor),
      width: 2,
    });
  }
  rings.show = options.samplingAreas;
  collection.add(rings);

  const hemisphereBaseColors: Color[] = [];
  if (options.shape === 'hemisphere') {
    const hemisphereImage = litStudImage();
    for (const { anchor, color, observation, size } of symbols) {
      const cesiumColor = Color.fromCssColorString(color).withAlpha(1);
      const placement = observationSurfacePlacement(
        anchor,
        observation,
        elevationFactor,
      );
      hemisphereBaseColors.push(cesiumColor.clone());
      hemispheres.add({
        alignedAxis: Cartesian3.ZERO,
        color: cesiumColor,
        disableDepthTestDistance: 0,
        eyeOffset: placement.eyeOffset,
        height: size * STUD_ASPECT_RATIO,
        id: observationPickId(observation.source_record_id),
        image: hemisphereImage,
        position: placement.position,
        sizeInMeters: false,
        verticalOrigin: VerticalOrigin.BOTTOM,
        width: size,
      });
    }
  }
  collection.add(hemispheres);

  const pinImage = options.shape === 'pin' ? litPinImage() : null;
  const pointBaseColors: Color[] = [];
  const pointOutlineBaseColors: Color[] = [];
  const pinBaseColors: Color[] = [];
  for (const symbol of symbols) {
    const { anchor, color, observation, size } = symbol;
    const cesiumColor = Color.fromCssColorString(color).withAlpha(0.97);
    const placement = observationSurfacePlacement(
      anchor,
      observation,
      elevationFactor,
    );
    if (options.shape === 'circle') {
      const outlineColor = Color.fromCssColorString('#071426').withAlpha(0.92);
      pointBaseColors.push(cesiumColor.clone());
      pointOutlineBaseColors.push(outlineColor.clone());
      points.add({
        color: cesiumColor,
        disableDepthTestDistance: 0,
        id: observationPickId(observation.source_record_id),
        outlineColor,
        outlineWidth: 2,
        pixelSize: size,
        position: placement.position,
      });
    } else if (options.shape === 'pin') {
      pinBaseColors.push(cesiumColor.clone());
      pins.add({
        alignedAxis: placement.normal,
        color: cesiumColor,
        disableDepthTestDistance: 0,
        eyeOffset: placement.eyeOffset,
        id: observationPickId(observation.source_record_id),
        height: size * PIN_ASPECT_RATIO,
        image: pinImage!,
        position: placement.position,
        sizeInMeters: false,
        verticalOrigin: VerticalOrigin.BOTTOM,
        width: size,
      });
    }
  }
  collection.add(points);
  collection.add(pins);

  const symbolCollections = [hemispheres, points, pins];
  return {
    collection,
    isReady: () => true,
    readyCount: () => 0,
    totalCount: () => 0,
    setElevationFactor(factor: number, force = false) {
      const safeFactor = Math.max(0, factor);
      if (safeFactor === elevationFactor) return;
      const now = performance.now();
      if (!force && safeFactor !== 0 && now - lastElevationUpdate < 50) return;
      elevationFactor = safeFactor;
      lastElevationUpdate = now;
      for (let index = 0; index < rings.length; index += 1)
        rings.get(index).positions = ringPositions(
          ringSamples[index],
          elevationFactor,
        );
      for (let index = 0; index < symbols.length; index += 1) {
        const symbol = symbols[index];
        const placement = observationSurfacePlacement(
          symbol.anchor,
          symbol.observation,
          elevationFactor,
        );
        if (options.shape === 'circle')
          points.get(index).position = placement.position;
        else if (options.shape === 'pin') {
          pins.get(index).position = placement.position;
          pins.get(index).alignedAxis = placement.normal;
        } else {
          hemispheres.get(index).position = placement.position;
        }
      }
    },
    setOpacity(opacity: number) {
      fadeOpacity = opacity;
      for (let index = 0; index < rings.length; index += 1) {
        const material = rings.get(index).material;
        const color = material.uniforms.color;
        if (color instanceof Color) {
          Color.clone(ringBaseColors[index], color);
          color.alpha =
            ringBaseColors[index].alpha * opacity * styleOpacity * earthOpacity;
        }
      }
      for (let index = 0; index < points.length; index += 1) {
        Color.clone(pointBaseColors[index], uploadColor);
        uploadColor.alpha =
          pointBaseColors[index].alpha * opacity * styleOpacity * earthOpacity;
        points.get(index).color = uploadColor;
        Color.clone(pointOutlineBaseColors[index], uploadColor);
        uploadColor.alpha =
          pointOutlineBaseColors[index].alpha *
          opacity *
          styleOpacity *
          earthOpacity;
        points.get(index).outlineColor = uploadColor;
      }
      for (let index = 0; index < pins.length; index += 1) {
        Color.clone(pinBaseColors[index], uploadColor);
        uploadColor.alpha =
          pinBaseColors[index].alpha * opacity * styleOpacity * earthOpacity;
        pins.get(index).color = uploadColor;
      }
      for (let index = 0; index < hemispheres.length; index += 1) {
        Color.clone(hemisphereBaseColors[index], uploadColor);
        uploadColor.alpha =
          hemisphereBaseColors[index].alpha *
          opacity *
          styleOpacity *
          earthOpacity;
        hemispheres.get(index).color = uploadColor;
      }
    },
    setEarthOpacity(opacity: number) {
      earthOpacity = Math.min(1, Math.max(0.15, opacity));
      this.setOpacity(fadeOpacity);
    },
    setSizeRange(range: ObservationSizeRange) {
      validateObservationSizeRange(options.shape, range);
      for (let index = 0; index < symbols.length; index += 1) {
        const symbol = symbols[index];
        const size = range[0] + symbol.sizePosition * (range[1] - range[0]);
        symbol.size = size;
        if (options.shape === 'circle') points.get(index).pixelSize = size;
        else if (options.shape === 'hemisphere') {
          hemispheres.get(index).width = size;
          hemispheres.get(index).height = size * STUD_ASPECT_RATIO;
        } else {
          pins.get(index).width = size;
          pins.get(index).height = size * PIN_ASPECT_RATIO;
        }
      }
    },
    setSamplingAreaColor(cssColor: string) {
      const selected = Color.fromCssColorString(cssColor).withAlpha(0.9);
      for (let index = 0; index < rings.length; index += 1)
        ringBaseColors[index] = selected.clone();
      this.setOpacity(fadeOpacity);
    },
    setStyleOpacity(opacity: number) {
      styleOpacity = opacity;
      this.setOpacity(fadeOpacity);
    },
    setVisibility(symbolsVisible: boolean, samplingAreas: boolean) {
      rings.show = samplingAreas;
      for (const symbolCollection of symbolCollections)
        symbolCollection.show = symbolsVisible;
    },
  };
}
