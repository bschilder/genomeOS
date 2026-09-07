/** Complete client explorer and load state machine for Atlas design §11. */

import 'cesium/Build/Cesium/Widgets/widgets.css';
import '../../styles/atlas.css';

import { useEffect, useMemo, useRef, useState } from 'react';

import type {
  ArtifactRef,
  AtlasCatalog,
  Observation,
  SurfaceCell,
} from '../../atlas/contracts';
import {
  createAtlasScene,
  resolveElevationView,
  type AtlasSceneController,
  type ContextStatus,
  type SceneCapabilities,
} from '../../atlas/scene/atlas-scene';
import type { ContextWarning } from '../../atlas/scene/context-controller';
import { StaticAtlasDataProvider } from '../../atlas/static-provider';
import {
  parseExplorerState,
  serializeExplorerState,
  type ExplorerSceneMode,
  type ExplorerState,
  type LayerId,
  type StateCorrection,
} from '../../atlas/url-state';
import { defaultPalette, type Metric } from '../../atlas/visual-encoding';
import { AtlasLegend } from './AtlasLegend';
import { AtlasStatus, type ExplorerLoadStatus } from './AtlasStatus';
import { ExplorerControls } from './ExplorerControls';
import { InspectorPanel, type InspectorSelection } from './InspectorPanel';

interface AtlasExplorerProps {
  cesiumToken?: string;
  dataBaseUrl: string;
}

function artifactVersion(ref: ArtifactRef): string {
  return `${ref.model_version}/${ref.data_version}`;
}

function message(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'An unexpected atlas error occurred.';
}

function displayKey(state: ExplorerState, reducedMotion: boolean): string {
  return [state.view, state.elevation, state.exaggeration, reducedMotion].join(
    ':',
  );
}

function supportsWebGL(): boolean {
  const canvas = document.createElement('canvas');
  return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
}

const PUBLIC_CAPABILITIES: SceneCapabilities = {
  basemaps: {
    'aerial-labels': false,
    aerial: false,
    'dark-streets': true,
    roads: false,
  },
  terrains: { 'smooth-globe': true, 'world-terrain': false },
};

export default function AtlasExplorer({
  cesiumToken = '',
  dataBaseUrl,
}: AtlasExplorerProps) {
  const provider = useMemo(
    () => new StaticAtlasDataProvider(dataBaseUrl),
    [dataBaseUrl],
  );
  const sceneElement = useRef<HTMLDivElement>(null);
  const scene = useRef<AtlasSceneController | null>(null);
  const surfaceCells = useRef<Map<string, SurfaceCell>>(new Map());
  const observations = useRef<Map<string, Observation>>(new Map());
  const requestSequence = useRef(0);
  const cameraApplied = useRef(false);
  const appliedDisplay = useRef<string | null>(null);
  const [sceneAttempt, setSceneAttempt] = useState(0);
  const [dataAttempt, setDataAttempt] = useState(0);
  const [catalog, setCatalog] = useState<AtlasCatalog | null>(null);
  const [state, setState] = useState<ExplorerState | null>(null);
  const [activeArtifact, setActiveArtifact] = useState<ArtifactRef | null>(
    null,
  );
  const [selection, setSelection] = useState<InspectorSelection | null>(null);
  const [status, setStatus] = useState<ExplorerLoadStatus>('loading catalog');
  const [contextStatus, setContextStatus] = useState<ContextStatus>('loading');
  const [sceneWarnings, setSceneWarnings] = useState<readonly ContextWarning[]>(
    [],
  );
  const [capabilities, setCapabilities] =
    useState<SceneCapabilities>(PUBLIC_CAPABILITIES);
  const [corrections, setCorrections] = useState<StateCorrection[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [webglFailed, setWebglFailed] = useState(false);
  const [viewNotice, setViewNotice] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setReducedMotion(media.matches);
    updatePreference();
    media.addEventListener('change', updatePreference);
    return () => media.removeEventListener('change', updatePreference);
  }, []);

  useEffect(() => {
    const element = sceneElement.current;
    if (!element) return;
    cameraApplied.current = false;
    appliedDisplay.current = null;
    setWebglFailed(false);
    if (!supportsWebGL()) {
      setWebglFailed(true);
      return;
    }
    try {
      const controller = createAtlasScene(element, {
        cesiumToken,
        naturalEarthUrl: `${dataBaseUrl}ne-110m-admin-0.geojson`,
        reducedMotion,
      });
      scene.current = controller;
      setCapabilities(controller.capabilities());
      const removePick = controller.onPick((pick) => {
        if (pick?.kind === 'surface') {
          const value = surfaceCells.current.get(pick.h3Index);
          setSelection(value ? { kind: 'surface', value } : null);
        } else if (pick?.kind === 'observation') {
          const value = observations.current.get(pick.sourceRecordId);
          setSelection(value ? { kind: 'observation', value } : null);
        } else setSelection(null);
      });
      const removeCamera = controller.onCameraSettled((camera) => {
        if (!cameraApplied.current) return;
        setState((current) => (current ? { ...current, camera } : current));
      });
      const removeContext = controller.onContextStatus(setContextStatus);
      const removeWarnings = controller.onWarning(setSceneWarnings);
      return () => {
        removePick();
        removeCamera();
        removeContext();
        removeWarnings();
        controller.destroy();
        scene.current = null;
      };
    } catch {
      setWebglFailed(true);
    }
  }, [cesiumToken, dataBaseUrl, reducedMotion, sceneAttempt]);

  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading catalog');
    setError(null);
    provider
      .getCatalog(controller.signal)
      .then((loaded) => {
        const parsed = parseExplorerState(window.location.search, loaded);
        setCatalog(loaded);
        setCorrections(parsed.corrections);
        setState(parsed.state);
        if (
          parsed.corrections.some(
            ({ field, reason }) =>
              field === 'entity' && reason === 'unavailable',
          )
        ) {
          setError(
            `The requested map “${parsed.state.entityId}” is not available in this catalog.`,
          );
        }
      })
      .catch((caught) => {
        if ((caught as Error).name !== 'AbortError') setError(message(caught));
      });
    return () => controller.abort();
  }, [provider, dataAttempt]);

  useEffect(() => {
    if (!catalog || !state || !scene.current || webglFailed) return;
    const ref = catalog.artifacts.find(
      (candidate) => candidate.id === state.entityId,
    );
    if (!ref || artifactVersion(ref) !== state.artifactVersion) {
      setError(
        `The requested map “${state.entityId}” at version “${state.artifactVersion || 'unspecified'}” is unavailable. Choose an available map to continue.`,
      );
      return;
    }

    const controller = new AbortController();
    const sequence = ++requestSequence.current;
    setStatus('loading artifact');
    setError(null);
    Promise.all([
      provider.getSurface(ref, controller.signal),
      provider.getObservations(ref, controller.signal),
    ])
      .then(async ([surface, measured]) => {
        if (sequence !== requestSequence.current) return;
        setStatus('validating');
        surfaceCells.current = new Map(
          surface.cells.map((cell) => [cell.h3_index, cell]),
        );
        observations.current = new Map(
          (measured?.observations ?? []).map((observation) => [
            observation.source_record_id,
            observation,
          ]),
        );
        setStatus('rendering');
        const controller = scene.current;
        if (!controller) return;
        await controller.setSceneMode(state.view, reducedMotion);
        if (
          sequence !== requestSequence.current ||
          controller !== scene.current
        )
          return;
        await controller.setElevation(state.elevation, state.exaggeration);
        if (
          sequence !== requestSequence.current ||
          controller !== scene.current
        )
          return;
        appliedDisplay.current = displayKey(state, reducedMotion);
        await controller.setArtifact(surface, measured);
        if (
          sequence !== requestSequence.current ||
          controller !== scene.current
        )
          return;
        if (!cameraApplied.current) {
          controller.setCamera(state.camera, !reducedMotion);
          cameraApplied.current = true;
        }
        setSelection(null);
        setActiveArtifact(ref);
        setStatus('ready');
      })
      .catch((caught) => {
        if (
          (caught as Error).name !== 'AbortError' &&
          sequence === requestSequence.current
        ) {
          setError(`${state.entityId}: ${message(caught)}`);
        }
      });
    return () => controller.abort();
  }, [
    catalog,
    provider,
    state?.artifactVersion,
    state?.entityId,
    webglFailed,
    dataAttempt,
    reducedMotion,
    sceneAttempt,
  ]);

  useEffect(() => {
    if (!state) return;
    const query = serializeExplorerState(state);
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}?${query}${window.location.hash}`,
    );
  }, [state]);

  useEffect(() => {
    if (state) void scene.current?.setMetric(state.metric);
  }, [state?.metric]);

  useEffect(() => {
    if (state)
      void scene.current?.setSurfaceStyle(
        state.surfacePalette,
        state.surfaceOpacity,
        state.cellEdges,
      );
  }, [state?.surfacePalette, state?.surfaceOpacity, state?.cellEdges]);

  useEffect(() => {
    if (state)
      void scene.current?.setObservationStyle({
        colorVariable: state.observationColor,
        hemisphereRange: state.observationHemisphereRange,
        pointRange: state.observationPointRange,
        samplingAreas: state.samplingAreas,
        shape: state.observationShape,
        sizeVariable: state.observationSize,
      });
  }, [
    state?.observationColor,
    state?.observationHemisphereRange,
    state?.observationPointRange,
    state?.observationShape,
    state?.observationSize,
    state?.samplingAreas,
  ]);

  useEffect(() => {
    if (state) void scene.current?.setBasemap(state.basemap);
  }, [state?.basemap, sceneAttempt]);

  useEffect(() => {
    if (state) void scene.current?.setTerrain(state.terrain);
  }, [state?.terrain, sceneAttempt]);

  useEffect(() => {
    if (state) scene.current?.setLayerVisibility(state.layers);
  }, [state?.layers]);

  useEffect(() => {
    if (!state || !activeArtifact || !scene.current) return;
    const key = displayKey(state, reducedMotion);
    if (appliedDisplay.current === key) return;
    const controller = scene.current;
    let canceled = false;
    setStatus('rendering');
    void (async () => {
      try {
        await controller.setSceneMode(state.view, reducedMotion);
        if (canceled || controller !== scene.current) return;
        await controller.setElevation(state.elevation, state.exaggeration);
        if (canceled || controller !== scene.current) return;
        appliedDisplay.current = key;
        setStatus('ready');
      } catch (caught) {
        if (!canceled) setError(message(caught));
      }
    })();
    return () => {
      canceled = true;
    };
  }, [
    activeArtifact?.id,
    reducedMotion,
    state?.elevation,
    state?.exaggeration,
    state?.view,
  ]);

  const update = (change: Partial<ExplorerState>) =>
    setState((current) => (current ? { ...current, ...change } : current));

  const chooseEntity = (id: string) => {
    const ref = catalog?.artifacts.find((candidate) => candidate.id === id);
    if (!ref) return;
    update({ artifactVersion: artifactVersion(ref), entityId: id });
  };

  const chooseLayer = (layer: LayerId, visible: boolean) => {
    setState((current) =>
      current
        ? { ...current, layers: { ...current.layers, [layer]: visible } }
        : current,
    );
  };

  const chooseElevation = (enabled: boolean) => {
    setViewNotice(null);
    setState((current) => {
      if (!current) return current;
      const view = resolveElevationView(current.view, enabled);
      if (view !== current.view) {
        setViewNotice(
          'Elevation needs an angled view, so the atlas moved from Map to Perspective.',
        );
      }
      return { ...current, elevation: enabled, view };
    });
  };

  return (
    <div
      className="atlas-explorer"
      data-atlas-explorer="AtlasExplorer"
      data-atlas-active={activeArtifact?.id ?? ''}
      data-atlas-ready={status === 'ready' ? 'true' : 'false'}
      role="application"
      aria-label="genomeOS globe explorer"
    >
      <div
        className="atlas-scene"
        ref={sceneElement}
        role="region"
        aria-label="Interactive globe canvas"
      />
      <div className="atlas-brand" aria-hidden="true">
        <span className="brand-name">genomeOS</span> atlas
      </div>

      {catalog && state ? (
        <ExplorerControls
          capabilities={capabilities}
          catalog={catalog}
          dataBaseUrl={dataBaseUrl}
          state={state}
          disabled={false}
          onEntity={chooseEntity}
          onExternalInfo={(source, signal) => {
            const selected = catalog.artifacts.find(
              (artifact) => artifact.id === state.entityId,
            );
            if (!selected || activeArtifact?.id !== selected.id)
              return Promise.reject(
                new Error('Wait for the selected map to finish loading.'),
              );
            return provider.getExternalInfo(selected, source, signal);
          }}
          onMetric={(metric: Metric) =>
            setState((current) =>
              current
                ? {
                    ...current,
                    metric,
                    surfacePalette:
                      current.paletteMode === 'metric-default'
                        ? defaultPalette(metric)
                        : current.surfacePalette,
                  }
                : current,
            )
          }
          onBasemap={(basemap) => update({ basemap })}
          onTerrain={(terrain) => update({ terrain })}
          onSurfacePalette={(surfacePalette) =>
            update({ paletteMode: 'custom', surfacePalette })
          }
          onSurfaceOpacity={(surfaceOpacity) => update({ surfaceOpacity })}
          onCellEdges={(cellEdges) => update({ cellEdges })}
          onObservationShape={(observationShape) =>
            update({ observationShape })
          }
          onObservationColor={(observationColor) =>
            update({ observationColor })
          }
          onObservationSize={(observationSize) => update({ observationSize })}
          onObservationPointRange={(observationPointRange) =>
            update({ observationPointRange })
          }
          onObservationHemisphereRange={(observationHemisphereRange) =>
            update({ observationHemisphereRange })
          }
          onSamplingAreas={(samplingAreas) => update({ samplingAreas })}
          onLayer={chooseLayer}
          onView={(view: ExplorerSceneMode) => update({ view })}
          onElevation={chooseElevation}
          onExaggeration={(exaggeration) => update({ exaggeration })}
          onHome={() => scene.current?.home(!reducedMotion)}
          onZoom={(direction) => scene.current?.zoom(direction)}
        />
      ) : (
        <aside className="atlas-controls atlas-controls--loading">
          <p className="atlas-kicker">Interactive atlas</p>
          <h1>Explore human genetic variation</h1>
          <p>Loading the public catalog…</p>
        </aside>
      )}

      <AtlasStatus
        status={status}
        contextStatus={contextStatus}
        sceneWarnings={sceneWarnings}
        corrections={corrections}
        error={error}
        webglFailed={webglFailed}
        onRetry={() => {
          if (webglFailed) setSceneAttempt((value) => value + 1);
          else setDataAttempt((value) => value + 1);
        }}
      />
      {viewNotice && (
        <p className="atlas-view-notice" role="status">
          {viewNotice}
        </p>
      )}
      {activeArtifact && state && (
        <AtlasLegend artifact={activeArtifact} state={state} />
      )}
      {activeArtifact && selection && (
        <InspectorPanel
          artifact={activeArtifact}
          selection={selection}
          onClose={() => {
            scene.current?.setSelection(null);
            setSelection(null);
          }}
        />
      )}
      <p className="atlas-data-credit">
        Scientific data and provenance:{' '}
        <a
          href="https://huggingface.co/datasets/bschilder/genomeos-data"
          target="_blank"
          rel="noreferrer"
        >
          <span className="brand-name">genomeOS</span> public dataset
        </a>
      </p>
    </div>
  );
}
