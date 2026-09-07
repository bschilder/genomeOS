/** Natural Earth country-outline lifecycle for Atlas design §11. */

import {
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  Credit,
  GeoJsonDataSource,
  type GeoJsonDataSource as GeoJsonSource,
  type Viewer,
} from 'cesium';

export class GeographicOverlay {
  readonly #viewer: Viewer;
  #source: GeoJsonSource | null = null;
  #visible = true;

  constructor(viewer: Viewer) {
    this.#viewer = viewer;
  }

  async load(url: string): Promise<'ready' | 'fallback'> {
    try {
      const source = await GeoJsonDataSource.load(url, {
        clampToGround: false,
        fill: Color.TRANSPARENT,
        stroke: Color.fromCssColorString('#4dc5df').withAlpha(0.46),
        strokeWidth: 1.2,
      });
      source.show = false;
      source.credit = new Credit(
        '<a href="https://www.naturalearthdata.com/" target="_blank">Natural Earth</a> (public domain)',
        true,
      );
      if (this.#viewer.isDestroyed()) return 'fallback';
      await this.#viewer.dataSources.add(source);
      const depthColor = new ColorMaterialProperty(
        Color.fromCssColorString('#8cecff').withAlpha(0.78),
      );
      for (const entity of source.entities.values) {
        if (!entity.polyline) continue;
        entity.polyline.clampToGround = new ConstantProperty(false);
        entity.polyline.depthFailMaterial = depthColor;
        entity.polyline.width = new ConstantProperty(1.65);
      }
      source.show = this.#visible;
      this.#source = source;
      return 'ready';
    } catch {
      return 'fallback';
    }
  }

  setVisible(visible: boolean): void {
    this.#visible = visible;
    if (this.#source) this.#source.show = visible;
  }
}
