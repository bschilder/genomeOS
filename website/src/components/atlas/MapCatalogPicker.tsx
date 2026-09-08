/** Searchable, explanatory Atlas map catalog for design §11. */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';

import '../../styles/map-catalog.css';

import type {
  ArtifactRef,
  AtlasCatalog,
  DiscoveryGroup,
} from '../../atlas/contracts';

interface MapCatalogPickerProps {
  catalog: AtlasCatalog;
  disabled: boolean;
  selectedId: string;
  onSelect: (id: string) => void;
}

interface PanelPosition extends CSSProperties {
  left: number;
  top: number;
  width: number;
}

function searchableText(artifact: ArtifactRef, group: DiscoveryGroup): string {
  return [
    artifact.label,
    artifact.discovery.symbol_expansion,
    artifact.discovery.relevance,
    artifact.discovery.map_measures,
    ...artifact.discovery.aliases,
    group.label,
    group.summary,
    group.biology,
  ]
    .join(' ')
    .toLocaleLowerCase();
}

function combinedReferences(
  artifact: ArtifactRef,
  group: DiscoveryGroup,
): ArtifactRef['discovery']['references'] {
  return [...artifact.discovery.references, ...group.references].filter(
    (reference, index, references) =>
      references.findIndex(({ url }) => url === reference.url) === index,
  );
}

export function MapCatalogPicker({
  catalog,
  disabled,
  selectedId,
  onSelect,
}: MapCatalogPickerProps) {
  const dialogId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [detailId, setDetailId] = useState(selectedId);
  const [position, setPosition] = useState<PanelPosition>({
    left: 428,
    top: 96,
    width: 720,
  });
  const selected = catalog.artifacts.find(({ id }) => id === selectedId);
  const groupById = useMemo(
    () => new Map(catalog.discovery_groups.map((group) => [group.id, group])),
    [catalog.discovery_groups],
  );
  const selectedGroup = selected
    ? groupById.get(selected.discovery.group_id)
    : undefined;

  const filteredGroups = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return catalog.discovery_groups
      .map((group) => ({
        group,
        artifacts: catalog.artifacts.filter(
          (artifact) =>
            artifact.discovery.group_id === group.id &&
            (!needle || searchableText(artifact, group).includes(needle)),
        ),
      }))
      .filter(({ artifacts }) => artifacts.length > 0);
  }, [catalog.artifacts, catalog.discovery_groups, query]);

  const visibleArtifacts = filteredGroups.flatMap(({ artifacts }) => artifacts);
  const detail =
    visibleArtifacts.find(({ id }) => id === detailId) ?? visibleArtifacts[0];
  const detailGroup = detail
    ? groupById.get(detail.discovery.group_id)
    : undefined;

  const placePanel = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const gutter = 12;
    const width = Math.min(720, window.innerWidth - gutter * 2);
    const roomOnRight = rect.right + gutter + width <= window.innerWidth;
    setPosition({
      left: roomOnRight
        ? rect.right + gutter
        : Math.max(gutter, window.innerWidth - width - gutter),
      top: Math.max(76, Math.min(rect.top, 104)),
      width,
    });
  }, []);

  const close = useCallback((restoreFocus = false) => {
    setOpen(false);
    setQuery('');
    if (restoreFocus)
      window.requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!open) return;
    placePanel();
    window.requestAnimationFrame(() => searchRef.current?.focus());
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
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('resize', placePanel);
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [close, open, placePanel]);

  const choose = (id: string) => {
    onSelect(id);
    setDetailId(id);
    close(true);
  };

  const moveListFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const options = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>(
        '[role="option"]',
      ),
    );
    if (!options.length) return;
    event.preventDefault();
    const current = Math.max(
      0,
      options.indexOf(document.activeElement as HTMLButtonElement),
    );
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? options.length - 1
          : event.key === 'ArrowUp'
            ? (current - 1 + options.length) % options.length
            : (current + 1) % options.length;
    options[next]?.focus();
  };

  return (
    <div className="atlas-map-catalog">
      <button
        aria-controls={dialogId}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Select dataset. Current dataset: ${selected?.label ?? selectedId}`}
        className="atlas-map-catalog__trigger"
        disabled={disabled}
        ref={triggerRef}
        type="button"
        onClick={() => {
          setDetailId(selectedId);
          setOpen((value) => !value);
        }}
      >
        <span>
          <small>{selectedGroup?.label ?? 'Unavailable map'}</small>
          <strong>{selected?.label ?? selectedId}</strong>
        </span>
        <span aria-hidden="true">{open ? '−' : '+'}</span>
      </button>

      {open &&
        createPortal(
          <div
            aria-labelledby={`${dialogId}-title`}
            aria-modal="false"
            className="atlas-map-picker"
            id={dialogId}
            ref={panelRef}
            role="dialog"
            style={position}
          >
            <header className="atlas-map-picker__header">
              <div>
                <p>Genetic variation catalog</p>
                <h2 id={`${dialogId}-title`}>Select dataset</h2>
              </div>
              <button
                aria-label="Close map catalog"
                type="button"
                onClick={() => close(true)}
              >
                ×
              </button>
            </header>

            <label className="atlas-map-picker__search">
              <span>Search maps</span>
              <input
                aria-label="Search maps"
                placeholder="Search symbols, biology, or disease relevance"
                ref={searchRef}
                role="searchbox"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>

            <div className="atlas-map-picker__body">
              <div
                aria-label="Available genetic maps"
                className="atlas-map-picker__index"
                role="listbox"
                onKeyDown={moveListFocus}
              >
                {filteredGroups.map(({ group, artifacts }) => (
                  <section
                    aria-labelledby={`${dialogId}-${group.id}`}
                    className="atlas-map-picker__group"
                    key={group.id}
                    role="group"
                  >
                    <div>
                      <h3 id={`${dialogId}-${group.id}`}>{group.label}</h3>
                      <span>{artifacts.length}</span>
                    </div>
                    <p>{group.summary}</p>
                    {artifacts.map((artifact) => (
                      <button
                        aria-selected={artifact.id === selectedId}
                        className="atlas-map-picker__option"
                        data-active={
                          artifact.id === detail?.id ? 'true' : 'false'
                        }
                        data-map-id={artifact.id}
                        key={artifact.id}
                        role="option"
                        type="button"
                        onClick={() => choose(artifact.id)}
                        onFocus={() => setDetailId(artifact.id)}
                        onPointerEnter={() => setDetailId(artifact.id)}
                      >
                        <strong>{artifact.label}</strong>
                        <span>{artifact.discovery.symbol_expansion}</span>
                      </button>
                    ))}
                  </section>
                ))}
                {filteredGroups.length === 0 && (
                  <p className="atlas-map-picker__empty">
                    No maps match “{query.trim()}”.
                  </p>
                )}
              </div>

              {detail && detailGroup && (
                <article
                  aria-live="polite"
                  className="atlas-map-picker__detail"
                >
                  <p className="atlas-map-picker__category">
                    {detailGroup.label}
                  </p>
                  <h3>{detail.label}</h3>
                  <p className="atlas-map-picker__expansion">
                    {detail.discovery.symbol_expansion}
                  </p>
                  <dl>
                    <div>
                      <dt>This map shows</dt>
                      <dd>{detail.discovery.map_measures}</dd>
                    </div>
                    <div>
                      <dt>Why it matters</dt>
                      <dd>{detail.discovery.relevance}</dd>
                    </div>
                    <div>
                      <dt>Biology</dt>
                      <dd>{detailGroup.biology}</dd>
                    </div>
                  </dl>
                  <p className="atlas-map-picker__caution">
                    Population patterns support research and education; they do
                    not diagnose an individual or predict personal disease risk.
                  </p>
                  <div className="atlas-map-picker__sources">
                    <span>Learn from primary sources</span>
                    {combinedReferences(detail, detailGroup).map(
                      (reference) => (
                        <a
                          href={reference.url}
                          key={`${reference.url}-${reference.label}`}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {reference.label}
                        </a>
                      ),
                    )}
                  </div>
                </article>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
