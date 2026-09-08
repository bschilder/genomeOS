/** Preview-tile basemap and terrain chooser for Atlas design §11. */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { createPortal } from 'react-dom';

import {
  BASEMAP_OPTIONS,
  TERRAIN_OPTIONS,
  basemapOption,
  terrainOption,
  type BasemapId,
  type EarthStyleOption,
  type TerrainId,
} from '../../atlas/earth-style-catalog';
import type { SceneCapabilities } from '../../atlas/scene/atlas-scene';
import { InfoTip } from './InfoTip';

interface EarthStylePickerProps {
  basemap: BasemapId;
  capabilities: SceneCapabilities;
  disabled: boolean;
  terrain: TerrainId;
  onBasemap: (value: BasemapId) => void;
  onTerrain: (value: TerrainId) => void;
}

interface PanelPosition extends CSSProperties {
  left: number;
  top: number;
  width: number;
}

type GalleryOption = EarthStyleOption<string> & {
  kind: 'basemap' | 'terrain';
};

const IMAGE_ROOT = `${import.meta.env.BASE_URL}cesium/Widgets/Images/`;
const HOVER_DELAY_MS = 90;

function thumbnail(option: EarthStyleOption<string>): string {
  return `${IMAGE_ROOT}${option.thumbnail}`;
}

function withKind(
  option: EarthStyleOption<string>,
  kind: GalleryOption['kind'],
): GalleryOption {
  return { ...option, kind };
}

function groupedBasemaps() {
  return (['genomeOS', 'Cesium ion', 'Other'] as const).map((category) => ({
    category,
    options: BASEMAP_OPTIONS.filter((option) => option.category === category),
  }));
}

export function EarthStylePicker({
  basemap,
  capabilities,
  disabled,
  terrain,
  onBasemap,
  onTerrain,
}: EarthStylePickerProps) {
  const dialogId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const hoverTimer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition>({
    left: 12,
    top: 76,
    width: 460,
  });
  const selectedBasemap = basemapOption(basemap);
  const selectedTerrain = terrainOption(terrain);
  const [detail, setDetail] = useState<GalleryOption>(() =>
    withKind(selectedBasemap, 'basemap'),
  );

  const placePanel = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const gutter = 12;
    const width = Math.min(472, window.innerWidth - gutter * 2);
    const roomOnRight = rect.right + gutter + width <= window.innerWidth;
    const left = roomOnRight
      ? rect.right + gutter
      : Math.max(gutter, rect.left - width - gutter);
    setPosition({
      left,
      top: Math.max(76, Math.min(rect.top, 96)),
      width,
    });
  }, []);

  const close = useCallback((restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus)
      window.requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!open) return;
    placePanel();
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        panelRef.current?.contains(target) ||
        triggerRef.current?.contains(target)
      )
        return;
      close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close(true);
    };
    window.addEventListener('resize', placePanel);
    window.addEventListener('scroll', placePanel, true);
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('resize', placePanel);
      window.removeEventListener('scroll', placePanel, true);
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [close, open, placePanel]);

  useEffect(
    () => () => {
      if (hoverTimer.current !== null) window.clearTimeout(hoverTimer.current);
    },
    [],
  );

  const queueDetail = (option: GalleryOption, immediate = false) => {
    if (hoverTimer.current !== null) window.clearTimeout(hoverTimer.current);
    if (immediate) {
      setDetail(option);
      return;
    }
    hoverTimer.current = window.setTimeout(
      () => setDetail(option),
      HOVER_DELAY_MS,
    );
  };

  const chooseBasemap = (id: BasemapId) => {
    if (!capabilities.basemaps[id]) return;
    onBasemap(id);
    close(true);
  };

  const chooseTerrain = (id: TerrainId) => {
    if (!capabilities.terrains[id]) return;
    onTerrain(id);
    close(true);
  };

  const galleryButton = (
    option: EarthStyleOption<string>,
    kind: GalleryOption['kind'],
  ) => {
    const available =
      kind === 'basemap'
        ? capabilities.basemaps[option.id as BasemapId]
        : capabilities.terrains[option.id as TerrainId];
    const selected =
      kind === 'basemap' ? option.id === basemap : option.id === terrain;
    const item = withKind(option, kind);
    return (
      <button
        aria-checked={selected}
        aria-disabled={!available}
        aria-label={`${option.label} ${kind}`}
        className="atlas-earth-picker__option"
        data-selected={selected ? 'true' : 'false'}
        key={option.id}
        role="radio"
        type="button"
        onClick={() =>
          kind === 'basemap'
            ? chooseBasemap(option.id as BasemapId)
            : chooseTerrain(option.id as TerrainId)
        }
        onFocus={() => queueDetail(item, true)}
        onPointerEnter={() => queueDetail(item)}
      >
        <span className="atlas-earth-picker__image">
          <img src={thumbnail(option)} alt="" />
          {!available && <span aria-hidden="true">◆</span>}
        </span>
        <span>{option.label}</span>
      </button>
    );
  };

  const detailAvailable =
    detail.kind === 'basemap'
      ? capabilities.basemaps[detail.id as BasemapId]
      : capabilities.terrains[detail.id as TerrainId];

  return (
    <div className="atlas-earth-style">
      <span className="atlas-field__title">
        <span>Basemap &amp; terrain</span>
        <InfoTip label="basemap and terrain gallery">
          Changes the geographic imagery and physical relief beneath the
          scientific layers. These choices never alter modeled values.
        </InfoTip>
      </span>
      <button
        aria-controls={dialogId}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="Choose basemap and terrain"
        className="atlas-earth-style__trigger"
        disabled={disabled}
        ref={triggerRef}
        type="button"
        onClick={() => {
          setDetail(withKind(selectedBasemap, 'basemap'));
          setOpen((value) => !value);
        }}
      >
        <span className="atlas-earth-style__preview" aria-hidden="true">
          <img src={thumbnail(selectedBasemap)} alt="" />
          <img src={thumbnail(selectedTerrain)} alt="" />
        </span>
        <span>
          <strong>{selectedBasemap.label}</strong>
          <small>{selectedTerrain.label}</small>
        </span>
        <span className="atlas-earth-style__chevron" aria-hidden="true">
          {open ? '−' : '+'}
        </span>
      </button>

      {open &&
        createPortal(
          <div
            aria-labelledby={`${dialogId}-title`}
            aria-modal="false"
            className="atlas-earth-picker"
            id={dialogId}
            ref={panelRef}
            role="dialog"
            style={position}
          >
            <header className="atlas-earth-picker__header">
              <div>
                <p>Earth appearance</p>
                <h2 id={`${dialogId}-title`}>Basemap and terrain</h2>
              </div>
              <button
                aria-label="Close basemap and terrain"
                type="button"
                onClick={() => close(true)}
              >
                ×
              </button>
            </header>

            <div className="atlas-earth-picker__detail" role="tooltip">
              <div>
                <strong>{detail.label}</strong>
                <span>{detail.provider}</span>
              </div>
              <p>{detail.description}</p>
              {!detailAvailable && (
                <em>Unavailable: this build has no Cesium ion token.</em>
              )}
            </div>

            <section aria-labelledby={`${dialogId}-basemap`}>
              <h3 id={`${dialogId}-basemap`}>Basemap</h3>
              <div className="atlas-earth-picker__groups">
                {groupedBasemaps().map(({ category, options }) => (
                  <div className="atlas-earth-picker__group" key={category}>
                    <h4>{category}</h4>
                    <div
                      aria-label={`${category} basemaps`}
                      className="atlas-earth-picker__grid"
                      role="radiogroup"
                    >
                      {options.map((option) =>
                        galleryButton(option, 'basemap'),
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section aria-labelledby={`${dialogId}-terrain`}>
              <h3 id={`${dialogId}-terrain`}>Terrain</h3>
              <div
                aria-label="Terrain"
                className="atlas-earth-picker__grid"
                role="radiogroup"
              >
                {TERRAIN_OPTIONS.map((option) =>
                  galleryButton(option, 'terrain'),
                )}
              </div>
            </section>
          </div>,
          document.body,
        )}
    </div>
  );
}
