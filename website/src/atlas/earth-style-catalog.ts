/** Stable basemap and terrain gallery metadata for Atlas design §11. */

export interface EarthStyleOption<T extends string> {
  id: T;
  label: string;
  category: 'genomeOS' | 'Cesium ion' | 'Other';
  provider: string;
  description: string;
  thumbnail: string;
  requiresIon: boolean;
}

export const BASEMAP_OPTIONS = [
  {
    id: 'dark-streets',
    label: 'genomeOS Dark',
    category: 'genomeOS',
    provider: 'OpenStreetMap',
    description: 'Muted streets tuned to keep scientific layers legible.',
    thumbnail: 'ImageryProviders/stadiaAlidadeSmoothDark.png',
    requiresIon: false,
  },
  {
    id: 'aerial',
    label: 'Bing Maps Aerial',
    category: 'Cesium ion',
    provider: 'Bing Maps via Cesium ion',
    description: 'Satellite and aerial imagery without map labels.',
    thumbnail: 'ImageryProviders/bingAerial.png',
    requiresIon: true,
  },
  {
    id: 'aerial-labels',
    label: 'Bing Aerial + Labels',
    category: 'Cesium ion',
    provider: 'Bing Maps via Cesium ion',
    description: 'Satellite and aerial imagery with reference labels.',
    thumbnail: 'ImageryProviders/bingAerialLabels.png',
    requiresIon: true,
  },
  {
    id: 'roads',
    label: 'Bing Maps Roads',
    category: 'Cesium ion',
    provider: 'Bing Maps via Cesium ion',
    description: 'A labeled road and place reference map.',
    thumbnail: 'ImageryProviders/bingRoads.png',
    requiresIon: true,
  },
  {
    id: 'sentinel-2',
    label: 'Sentinel-2',
    category: 'Cesium ion',
    provider: 'EOX / Copernicus via Cesium ion',
    description: 'Cloudless Sentinel-2 composite from 2016–2017.',
    thumbnail: 'ImageryProviders/sentinel-2.png',
    requiresIon: true,
  },
  {
    id: 'blue-marble',
    label: 'Blue Marble',
    category: 'Cesium ion',
    provider: 'NASA via Cesium ion',
    description: 'NASA Blue Marble Next Generation imagery from July 2004.',
    thumbnail: 'ImageryProviders/blueMarble.png',
    requiresIon: true,
  },
  {
    id: 'earth-at-night',
    label: 'Earth at Night',
    category: 'Cesium ion',
    provider: 'NASA via Cesium ion',
    description: 'NASA Black Marble nighttime light composite.',
    thumbnail: 'ImageryProviders/earthAtNight.png',
    requiresIon: true,
  },
  {
    id: 'natural-earth-ii',
    label: 'Natural Earth II',
    category: 'Cesium ion',
    provider: 'Natural Earth / bundled locally',
    description: 'A quiet, darkened physical map with global coverage.',
    thumbnail: 'ImageryProviders/naturalEarthII.png',
    requiresIon: false,
  },
  {
    id: 'google-satellite',
    label: 'Google Satellite',
    category: 'Cesium ion',
    provider: 'Google Maps via Cesium ion',
    description: 'Global satellite imagery from Google Maps.',
    thumbnail: 'ImageryProviders/googleSatellite.png',
    requiresIon: true,
  },
  {
    id: 'google-satellite-labels',
    label: 'Google Satellite + Labels',
    category: 'Cesium ion',
    provider: 'Google Maps via Cesium ion',
    description: 'Google satellite imagery with place labels.',
    thumbnail: 'ImageryProviders/googleSatelliteLabels.png',
    requiresIon: true,
  },
  {
    id: 'google-roadmap',
    label: 'Google Roadmap',
    category: 'Cesium ion',
    provider: 'Google Maps via Cesium ion',
    description: 'Labeled roads and landscape features from Google Maps.',
    thumbnail: 'ImageryProviders/googleRoadmap.png',
    requiresIon: true,
  },
  {
    id: 'google-contour',
    label: 'Google Contour',
    category: 'Cesium ion',
    provider: 'Google Maps via Cesium ion',
    description: 'Hillshade, contour lines, and natural features.',
    thumbnail: 'ImageryProviders/googleContour.png',
    requiresIon: true,
  },
  {
    id: 'azure-aerial',
    label: 'Azure Maps Aerial',
    category: 'Cesium ion',
    provider: 'Azure Maps via Cesium ion',
    description: 'Global satellite and aerial imagery from Azure Maps.',
    thumbnail: 'ImageryProviders/azureAerial.png',
    requiresIon: true,
  },
  {
    id: 'azure-roads',
    label: 'Azure Maps Roads',
    category: 'Cesium ion',
    provider: 'Azure Maps via Cesium ion',
    description: 'Labeled roads and landscape features from Azure Maps.',
    thumbnail: 'ImageryProviders/azureRoads.png',
    requiresIon: true,
  },
  {
    id: 'arcgis-imagery',
    label: 'ArcGIS World Imagery',
    category: 'Other',
    provider: 'Esri ArcGIS',
    description: 'Satellite and aerial imagery assembled by Esri.',
    thumbnail: 'ImageryProviders/ArcGisMapServiceWorldImagery.png',
    requiresIon: false,
  },
  {
    id: 'arcgis-hillshade',
    label: 'ArcGIS World Hillshade',
    category: 'Other',
    provider: 'Esri ArcGIS',
    description: 'Global elevation portrayed as shaded relief.',
    thumbnail: 'ImageryProviders/ArcGisMapServiceWorldHillshade.png',
    requiresIon: false,
  },
  {
    id: 'esri-ocean',
    label: 'Esri World Ocean',
    category: 'Other',
    provider: 'Esri ArcGIS',
    description: 'Marine bathymetry with a restrained land reference map.',
    thumbnail: 'ImageryProviders/ArcGisMapServiceWorldOcean.png',
    requiresIon: false,
  },
  {
    id: 'openstreetmap',
    label: 'OpenStreetMap',
    category: 'Other',
    provider: 'OpenStreetMap contributors',
    description: 'The collaborative, editable street map of the world.',
    thumbnail: 'ImageryProviders/openStreetMap.png',
    requiresIon: false,
  },
  {
    id: 'stadia-watercolor',
    label: 'Stamen Watercolor',
    category: 'Other',
    provider: 'Stadia Maps / Stamen Design',
    description: 'A hand-painted cartographic treatment with organic edges.',
    thumbnail: 'ImageryProviders/stamenWatercolor.png',
    requiresIon: false,
  },
  {
    id: 'stadia-toner',
    label: 'Stamen Toner',
    category: 'Other',
    provider: 'Stadia Maps / Stamen Design',
    description: 'High-contrast monochrome streets and labels.',
    thumbnail: 'ImageryProviders/stamenToner.png',
    requiresIon: false,
  },
  {
    id: 'stadia-smooth',
    label: 'Stadia Alidade Smooth',
    category: 'Other',
    provider: 'Stadia Maps',
    description: 'A muted reference map designed for data overlays.',
    thumbnail: 'ImageryProviders/stadiaAlidadeSmooth.png',
    requiresIon: false,
  },
  {
    id: 'stadia-dark',
    label: 'Stadia Alidade Dark',
    category: 'Other',
    provider: 'Stadia Maps',
    description: 'A dark, low-noise reference map for bright overlays.',
    thumbnail: 'ImageryProviders/stadiaAlidadeSmoothDark.png',
    requiresIon: false,
  },
] as const satisfies readonly EarthStyleOption<string>[];

export const TERRAIN_OPTIONS = [
  {
    id: 'smooth-globe',
    label: 'Smooth Globe',
    category: 'genomeOS',
    provider: 'WGS84 ellipsoid',
    description: 'A mathematically smooth globe without physical relief.',
    thumbnail: 'TerrainProviders/Ellipsoid.png',
    requiresIon: false,
  },
  {
    id: 'world-terrain',
    label: 'Cesium World Terrain',
    category: 'Cesium ion',
    provider: 'Cesium ion',
    description: 'High-resolution global terrain with water and normals.',
    thumbnail: 'TerrainProviders/CesiumWorldTerrain.png',
    requiresIon: true,
  },
] as const satisfies readonly EarthStyleOption<string>[];

export type BasemapId = (typeof BASEMAP_OPTIONS)[number]['id'];
export type TerrainId = (typeof TERRAIN_OPTIONS)[number]['id'];

export const BASEMAP_IDS = BASEMAP_OPTIONS.map(({ id }) => id);
export const TERRAIN_IDS = TERRAIN_OPTIONS.map(({ id }) => id);

export function basemapOption(id: BasemapId) {
  return BASEMAP_OPTIONS.find((option) => option.id === id)!;
}

export function terrainOption(id: TerrainId) {
  return TERRAIN_OPTIONS.find((option) => option.id === id)!;
}
