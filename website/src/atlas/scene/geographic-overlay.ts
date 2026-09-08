/** Surface-following Natural Earth context for Atlas design §11. */

import { gridDisk, latLngToCell } from 'h3-js';
import {
  Cartesian3,
  Cartographic,
  Color,
  ColorMaterialProperty,
  ConstantPositionProperty,
  ConstantProperty,
  Credit,
  DistanceDisplayCondition,
  GeoJsonDataSource,
  type GeoJsonDataSource as GeoJsonSource,
  JulianDate,
  LabelGraphics,
  LabelStyle,
  NearFarScalar,
  PolylineGraphics,
  type Viewer,
} from 'cesium';

import type { SurfaceArtifact, SurfaceCell } from '../contracts';
import { heightForCell, type Metric } from '../visual-encoding';

interface CountryProperties {
  ADMIN?: unknown;
  LABEL_X?: unknown;
  LABEL_Y?: unknown;
  MIN_LABEL?: unknown;
  NAME?: unknown;
  NAME_LONG?: unknown;
}

interface BorderDefinition {
  coordinates: readonly [number, number][];
  graphics: PolylineGraphics;
  surfaceHeights: number[];
}

interface LabelDefinition {
  lat: number;
  lon: number;
  position: ConstantPositionProperty;
  surfaceHeight: number;
}

const BORDER_CLEARANCE_METRES = 1_800;
const LABEL_CLEARANCE_METRES = 2_500;
const FRONT_HEMISPHERE_DEPTH_TEST_LIMIT_METRES = 8_000_000;

export function countryLabelHeight(
  surfaceHeight: number,
  elevationFactor: number,
): number {
  return (
    Math.max(0, surfaceHeight) * Math.max(0, elevationFactor) +
    LABEL_CLEARANCE_METRES
  );
}

export function countryLabelText(properties: CountryProperties): string | null {
  for (const value of [properties.NAME_LONG, properties.ADMIN, properties.NAME])
    if (typeof value === 'string' && value.trim()) return value.trim();
  return null;
}

export function countryLabelDistanceForScale(minLabel: number): number {
  const safeLabel = Number.isFinite(minLabel) ? Math.max(0, minLabel) : 7;
  return Math.max(800_000, 45_000_000 / 2 ** (safeLabel * 0.75));
}

export function countryLabelDepthTestDistance(minLabel: number): number {
  return Math.min(
    countryLabelDistanceForScale(minLabel),
    FRONT_HEMISPHERE_DEPTH_TEST_LIMIT_METRES,
  );
}

function coordinatePair(position: Cartesian3): [number, number] {
  const cartographic = Cartographic.fromCartesian(position);
  return [
    (cartographic.longitude * 180) / Math.PI,
    (cartographic.latitude * 180) / Math.PI,
  ];
}

function supportedSurfaceHeight(
  lat: number,
  lon: number,
  surface: SurfaceArtifact,
  cells: ReadonlyMap<string, SurfaceCell>,
  metric: Metric,
): number {
  const index = latLngToCell(lat, lon, surface.artifact.resolution);
  let height = 0;
  for (const candidate of gridDisk(index, 1)) {
    const cell = cells.get(candidate);
    if (cell)
      height = Math.max(
        height,
        heightForCell(cell, surface.artifact.metric_domains[metric], 1, metric),
      );
  }
  return height;
}

function raisedPositions(
  coordinates: readonly [number, number][],
  surfaceHeights: readonly number[],
  elevationFactor: number,
): Cartesian3[] {
  return coordinates.map(([lon, lat], index) =>
    Cartesian3.fromDegrees(
      lon,
      lat,
      surfaceHeights[index] * elevationFactor + BORDER_CLEARANCE_METRES,
    ),
  );
}

export class GeographicOverlay {
  readonly #viewer: Viewer;
  readonly #borders: BorderDefinition[] = [];
  readonly #labels: LabelDefinition[] = [];
  readonly #borderMaterial = new ColorMaterialProperty(
    Color.WHITE.withAlpha(0.5),
  );
  #source: GeoJsonSource | null = null;
  #surface: SurfaceArtifact | null = null;
  #metric: Metric = 'post_mean';
  #elevationFactor = 0;
  #visible = true;

  constructor(viewer: Viewer) {
    this.#viewer = viewer;
  }

  async load(url: string): Promise<'ready' | 'fallback'> {
    try {
      const source = await GeoJsonDataSource.load(url, {
        clampToGround: false,
        fill: Color.TRANSPARENT,
        stroke: Color.TRANSPARENT,
        strokeWidth: 0,
      });
      source.show = false;
      this.#viewer.creditDisplay.addStaticCredit(
        new Credit(
          '<a href="https://www.naturalearthdata.com/" target="_blank">Natural Earth</a> (public domain)',
          true,
        ),
      );
      if (this.#viewer.isDestroyed()) return 'fallback';
      await this.#viewer.dataSources.add(source);
      const labeledCountries = new Set<string>();
      for (const entity of source.entities.values) {
        const hierarchy = entity.polygon?.hierarchy?.getValue(JulianDate.now());
        if (hierarchy && hierarchy.positions.length > 1) {
          entity.polygon!.show = new ConstantProperty(false);
          const coordinates = [
            ...hierarchy.positions.map(coordinatePair),
            coordinatePair(hierarchy.positions[0]),
          ];
          const graphics = new PolylineGraphics({
            clampToGround: false,
            material: this.#borderMaterial,
            positions: raisedPositions(
              coordinates,
              coordinates.map(() => 0),
              0,
            ),
            width: 1.65,
          });
          entity.polyline = graphics;
          this.#borders.push({
            coordinates,
            graphics,
            surfaceHeights: coordinates.map(() => 0),
          });
        }
        const properties = entity.properties?.getValue(JulianDate.now()) as
          CountryProperties | undefined;
        const text = properties ? countryLabelText(properties) : null;
        const lon = properties?.LABEL_X;
        const lat = properties?.LABEL_Y;
        if (
          !text ||
          labeledCountries.has(text) ||
          typeof lon !== 'number' ||
          !Number.isFinite(lon) ||
          typeof lat !== 'number' ||
          !Number.isFinite(lat)
        )
          continue;
        labeledCountries.add(text);
        const minLabel =
          typeof properties?.MIN_LABEL === 'number' ? properties.MIN_LABEL : 7;
        const position = new ConstantPositionProperty(
          Cartesian3.fromDegrees(lon, lat, LABEL_CLEARANCE_METRES),
        );
        entity.position = position;
        entity.label = new LabelGraphics({
          disableDepthTestDistance: countryLabelDepthTestDistance(minLabel),
          distanceDisplayCondition: new DistanceDisplayCondition(
            0,
            countryLabelDistanceForScale(minLabel),
          ),
          fillColor: Color.WHITE,
          font: '600 17px Inter, system-ui, sans-serif',
          outlineColor: Color.fromCssColorString('#020712').withAlpha(0.98),
          outlineWidth: 5,
          scaleByDistance: new NearFarScalar(1_000_000, 1.08, 24_000_000, 0.76),
          style: LabelStyle.FILL_AND_OUTLINE,
          text,
        });
        this.#labels.push({ lat, lon, position, surfaceHeight: 0 });
      }
      source.show = this.#visible;
      this.#source = source;
      this.#refreshSurfaceHeights();
      return 'ready';
    } catch (error) {
      console.warn('Geographic reference overlay could not be loaded.', error);
      return 'fallback';
    }
  }

  #refreshSurfaceHeights(): void {
    const surface = this.#surface;
    if (surface) {
      const cells = new Map(surface.cells.map((cell) => [cell.h3_index, cell]));
      for (const border of this.#borders)
        border.surfaceHeights = border.coordinates.map(([lon, lat]) =>
          supportedSurfaceHeight(lat, lon, surface, cells, this.#metric),
        );
      for (const label of this.#labels)
        label.surfaceHeight = supportedSurfaceHeight(
          label.lat,
          label.lon,
          surface,
          cells,
          this.#metric,
        );
    }
    this.#applyElevation();
  }

  #applyElevation(): void {
    for (const border of this.#borders)
      border.graphics.positions = new ConstantProperty(
        raisedPositions(
          border.coordinates,
          border.surfaceHeights,
          this.#elevationFactor,
        ),
      );
    for (const label of this.#labels)
      label.position.setValue(
        Cartesian3.fromDegrees(
          label.lon,
          label.lat,
          countryLabelHeight(label.surfaceHeight, this.#elevationFactor),
        ),
      );
    this.#viewer.scene.requestRender();
  }

  setSurface(surface: SurfaceArtifact, metric: Metric): void {
    this.#surface = surface;
    this.#metric = metric;
    this.#refreshSurfaceHeights();
  }

  setElevationFactor(factor: number): void {
    this.#elevationFactor = Math.max(0, factor);
    this.#applyElevation();
  }

  setVisible(visible: boolean): void {
    this.#visible = visible;
    if (this.#source) this.#source.show = visible;
  }

  setBorderStyle(cssColor: string, opacity: number): void {
    this.#borderMaterial.color = new ConstantProperty(
      Color.fromCssColorString(cssColor).withAlpha(
        Math.min(1, Math.max(0, opacity)),
      ),
    );
    this.#viewer.scene.requestRender();
  }
}
