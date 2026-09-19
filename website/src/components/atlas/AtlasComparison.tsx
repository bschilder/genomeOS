/** Visual juxtaposition of published maps; no cross-trait inference (design §11). */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AtlasCatalog } from '../../atlas/contracts';
import {
  comparisonQueries,
  comparisonSearch,
  sameNavigation,
  type SharedNavigation,
} from '../../atlas/comparison';
import { StaticAtlasDataProvider } from '../../atlas/static-provider';
import {
  parseExplorerState,
  serializeExplorerState,
  type ExplorerState,
} from '../../atlas/url-state';
import AtlasExplorer from './AtlasExplorer';
import { AtlasScope } from './AtlasScope';
import '../../styles/atlas-comparison.css';

interface Props {
  dataBaseUrl: string;
  cesiumToken?: string;
}

function validateSelection(query: string, catalog: AtlasCatalog): void {
  const params = new URLSearchParams(query);
  const artifact = catalog.artifacts.find(
    (ref) => ref.id === params.get('entity'),
  );
  if (!artifact)
    throw new Error(`Requested map is unavailable: ${params.get('entity')}`);
  if (
    params.get('version') !==
    `${artifact.model_version}/${artifact.data_version}`
  )
    throw new Error(
      `Requested artifact version is unavailable for ${artifact.label}.`,
    );
  if (parseExplorerState(query, catalog).corrections.length)
    throw new Error(
      'Invalid comparison state. No selection or setting was substituted.',
    );
}

export default function AtlasComparison({ dataBaseUrl, cesiumToken }: Props) {
  const provider = useMemo(
    () => new StaticAtlasDataProvider(dataBaseUrl, 120_000),
    [dataBaseUrl],
  );
  const [preparing, setPreparing] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<AtlasCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState('');
  const [leftReady, setLeftReady] = useState(false);
  const leftBecameReady = useCallback(() => setLeftReady(true), []);
  const [right, setRight] = useState('');
  const [queries, setQueries] = useState<{
    left: string;
    right: string;
  } | null>(null);
  const [navigation, setNavigation] = useState<SharedNavigation>();
  const shared = useRef<SharedNavigation | undefined>(undefined);
  const panelStates = useRef<Partial<Record<'left' | 'right', ExplorerState>>>(
    {},
  );
  useEffect(() => {
    const controller = new AbortController();
    void provider
      .getCatalog(controller.signal)
      .then(async (loaded) => {
        setCatalog(loaded);
        const requested = comparisonQueries(window.location.search);
        if (requested) {
          validateSelection(requested.left, loaded);
          validateSelection(requested.right, loaded);
          await prepare(requested, loaded, controller.signal);
        }
      })
      .catch((caught) => {
        if (caught.name !== 'AbortError') setError(String(caught.message));
      });
    return () => controller.abort();
  }, [provider]);

  const changed = useCallback(
    (panel: 'left' | 'right', state: ExplorerState) => {
      panelStates.current[panel] = state;
      if (!shared.current || !sameNavigation(shared.current, state)) {
        const next = { source: panel, camera: state.camera, view: state.view };
        shared.current = next;
        setNavigation(next);
      }
      const { left: a, right: b } = panelStates.current;
      if (a && b) {
        const search = comparisonSearch(
          serializeExplorerState(a),
          serializeExplorerState(b),
        );
        window.history.replaceState(
          null,
          '',
          `${window.location.pathname}?${search}`,
        );
      }
    },
    [],
  );
  const leftChanged = useCallback(
    (state: ExplorerState) => changed('left', state),
    [changed],
  );
  const rightChanged = useCallback(
    (state: ExplorerState) => changed('right', state),
    [changed],
  );

  async function prepare(
    selected: { left: string; right: string },
    loaded: AtlasCatalog,
    signal?: AbortSignal,
  ) {
    try {
      for (const query of [selected.left, selected.right]) {
        validateSelection(query, loaded);
        const ref = loaded.artifacts.find(
          (item) => item.id === new URLSearchParams(query).get('entity'),
        )!;
        setPreparing(
          `Loading and validating ${ref.label} before starting the maps…`,
        );
        await provider.getSurface(ref, signal);
        await provider.getObservations(ref, signal);
      }
      if (signal?.aborted) return;
      setQueries(selected);
    } finally {
      setPreparing(null);
    }
  }

  async function start() {
    if (!catalog) return;
    try {
      const makeQuery = (id: string) => {
        const ref = catalog!.artifacts.find((item) => item.id === id);
        if (!ref) throw new Error('Select both maps explicitly.');
        return new URLSearchParams({
          entity: id,
          version: `${ref.model_version}/${ref.data_version}`,
          edges: 'false',
          geometry: 'hexagons',
        }).toString();
      };
      const selected = { left: makeQuery(left), right: makeQuery(right) };
      validateSelection(selected.left, catalog);
      validateSelection(selected.right, catalog);
      setLeftReady(false);
      panelStates.current = {};
      shared.current = undefined;
      setNavigation(undefined);
      await prepare(selected, catalog);
      setError(null);
    } catch (caught) {
      setError((caught as Error).message);
    }
  }

  return (
    <main className="atlas-comparison">
      <header className="atlas-comparison-intro">
        <h1>Compare geographic evidence</h1>
        <p>
          Navigation is synchronized. Each map keeps its own measurement, color
          scale, uncertainty, support mask and versions. Similar colors or
          patterns do not establish trait correlation or pleiotropy.
        </p>
        <p>
          Numerical differences and genetic relationships are unavailable: no
          qualified comparison analysis is attached.
        </p>
        {!queries && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void start();
            }}
          >
            {(['left', 'right'] as const).map((panel) => (
              <label key={panel}>
                {panel === 'left' ? 'Left map' : 'Right map'}
                <select
                  value={panel === 'left' ? left : right}
                  required
                  onChange={(event) =>
                    (panel === 'left' ? setLeft : setRight)(event.target.value)
                  }
                >
                  <option value="">Select a published map</option>
                  {catalog?.artifacts.map((ref) => (
                    <option key={ref.id} value={ref.id}>
                      {ref.label} — {ref.measurement} — {ref.model_version}/
                      {ref.data_version}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <button disabled={!catalog || Boolean(preparing)}>
              Compare maps
            </button>
          </form>
        )}
        {preparing && <p role="status">{preparing}</p>}
        {error && <p role="alert">{error}</p>}
      </header>
      {queries && !error && (
        <div className="atlas-comparison-panels">
          <AtlasScope.Provider value="comparison-left">
            <section id="comparison-left" aria-label="Left evidence map">
              <div data-atlas-status-slot />
              <div data-atlas-external-slot />
              <h2>Left map — independent scale</h2>
              <AtlasExplorer
                key={`left:${queries.left}`}
                panel="left"
                onReady={leftBecameReady}
                initialQuery={queries.left}
                writeUrl={false}
                navigation={navigation}
                onStateChange={leftChanged}
                dataProvider={provider}
                dataBaseUrl={dataBaseUrl}
                cesiumToken={cesiumToken}
              />
            </section>
          </AtlasScope.Provider>
          <AtlasScope.Provider value="comparison-right">
            <section id="comparison-right" aria-label="Right evidence map">
              <div data-atlas-status-slot />
              <div data-atlas-external-slot />
              <h2>Right map — independent scale</h2>
              {leftReady ? (
                <AtlasExplorer
                  key={`right:${queries.right}`}
                  panel="right"
                  initialQuery={queries.right}
                  writeUrl={false}
                  navigation={navigation}
                  onStateChange={rightChanged}
                  dataProvider={provider}
                  dataBaseUrl={dataBaseUrl}
                  cesiumToken={cesiumToken}
                />
              ) : (
                <p role="status">
                  Waiting for the first map to finish rendering before starting
                  the second.
                </p>
              )}
            </section>
          </AtlasScope.Provider>
        </div>
      )}
    </main>
  );
}
