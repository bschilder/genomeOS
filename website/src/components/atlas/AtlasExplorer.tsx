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
  observationColorEncoding,
  observationDomains,
  type ObservationColorEncoding,
} from '../../atlas/observation-encoding';
import {
  nearestPlaceContext,
  populatedPlaceCatalogSchema,
  type ObservationPlaceContext,
  type PopulatedPlaceCatalog,
} from '../../atlas/place-context';
import {
  createAtlasScene,
  resolveElevationView,
  type AtlasSceneController,
  type ContextStatus,
  type SceneCapabilities,
} from '../../atlas/scene/atlas-scene';
import {
  availableBasemaps,
  availableTerrains,
  type ContextWarning,
} from '../../atlas/scene/context-controller';
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
import { HoverPreview } from './HoverPreview';
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
  basemaps: availableBasemaps(''),
  terrains: availableTerrains(''),
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
  const placeCatalogRequest = useRef<Promise<PopulatedPlaceCatalog> | null>(
    null,
  );
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
  const [hover, setHover] = useState<{
    position: { x: number; y: number };
    selection: InspectorSelection;
  } | null>(null);
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
  const [placeCatalog, setPlaceCatalog] =
    useState<PopulatedPlaceCatalog | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);
  const activeObservationDomains = useMemo(() => {
    if (!activeArtifact || observations.current.size === 0) return null;
    return observationDomains([...observations.current.values()]);
  }, [activeArtifact]);
  const colorEncodingFor = (
    candidate: InspectorSelection | null,
  ): ObservationColorEncoding | null => {
    if (!candidate || candidate.kind !== 'observation' || !state) return null;
    const colorDomain =
      state.observationColor === 'gradient'
        ? activeObservationDomains?.frequency
        : state.observationColor === 'ac'
          ? activeObservationDomains?.ac
          : ([0, 1] as const);
    if (!colorDomain) return null;
    return observationColorEncoding(
      candidate.value,
      state.observationColor,
      colorDomain,
      state.observationSolidColor,
      state.observationGradient,
    );
  };
  const placeContextFor = (
    candidate: InspectorSelection | null,
  ): ObservationPlaceContext | null => {
    if (!placeCatalog || !candidate || candidate.kind !== 'observation')
      return null;
    return nearestPlaceContext(candidate.value, placeCatalog);
  };
  const wantsPlaceContext =
    hover?.selection.kind === 'observation' ||
    selection?.kind === 'observation';

  useEffect(() => {
    if (!wantsPlaceContext || placeCatalog) return;
    let active = true;
    const request =
      placeCatalogRequest.current ??
      fetch(`${dataBaseUrl}ne-50m-populated-places.json`)
        .then((response) => {
          if (!response.ok)
            throw new Error(
              `Place context request failed (${response.status}).`,
            );
          return response.json();
        })
        .then((value) => populatedPlaceCatalogSchema.parse(value));
    placeCatalogRequest.current = request;
    void request
      .then((value) => {
        if (active) setPlaceCatalog(value);
      })
      .catch((caught) => {
        placeCatalogRequest.current = null;
        console.warn(
          'Optional observation place context is unavailable.',
          caught,
        );
      });
    return () => {
      active = false;
    };
  }, [dataBaseUrl, placeCatalog, wantsPlaceContext]);

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
        naturalEarthUrl: `${dataBaseUrl}ne-50m-admin-0.geojson`,
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
      const removeHover = controller.onHover((hovered) => {
        if (hovered?.pick.kind === 'surface') {
          const value = surfaceCells.current.get(hovered.pick.h3Index);
          setHover(
            value
              ? {
                  position: hovered.screenPosition,
                  selection: { kind: 'surface', value },
                }
              : null,
          );
        } else if (hovered?.pick.kind === 'observation') {
          const value = observations.current.get(hovered.pick.sourceRecordId);
          setHover(
            value
              ? {
                  position: hovered.screenPosition,
                  selection: { kind: 'observation', value },
                }
              : null,
          );
        } else setHover(null);
      });
      const removeCamera = controller.onCameraSettled((camera) => {
        if (!cameraApplied.current) return;
        setState((current) => (current ? { ...current, camera } : current));
      });
      const removeContext = controller.onContextStatus(setContextStatus);
      const removeWarnings = controller.onWarning(setSceneWarnings);
      return () => {
        removePick();
        removeHover();
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
        setHover(null);
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
        state.edgeColorMode,
        state.edgeFixedColor,
        state.surfaceGeometry,
      );
  }, [
    state?.surfacePalette,
    state?.surfaceOpacity,
    state?.cellEdges,
    state?.edgeColorMode,
    state?.edgeFixedColor,
    state?.surfaceGeometry,
  ]);

  useEffect(() => {
    if (state)
      void scene.current?.setObservationStyle({
        colorVariable: state.observationColor,
        gradient: state.observationGradient,
        opacity: state.observationOpacity,
        samplingAreaColor: state.samplingAreaColor,
        sizeRange: state.observationSizeRange,
        samplingAreas: state.samplingAreas,
        shape: state.observationShape,
        sizeVariable: state.observationSize,
        solidColor: state.observationSolidColor,
      });
  }, [
    state?.observationColor,
    state?.observationGradient,
    state?.observationOpacity,
    state?.samplingAreaColor,
    state?.observationSizeRange,
    state?.observationShape,
    state?.observationSize,
    state?.observationSolidColor,
    state?.samplingAreas,
  ]);

  useEffect(() => {
    if (state) void scene.current?.setBasemap(state.basemap);
  }, [state?.basemap, sceneAttempt]);

  useEffect(() => {
    if (state)
      scene.current?.setMapPresentation(
        state.basemapOpacity,
        state.basemapBrightness,
        state.dayNightLighting,
      );
  }, [
    state?.basemapOpacity,
    state?.basemapBrightness,
    state?.dayNightLighting,
    sceneAttempt,
  ]);

  useEffect(() => {
    if (state) void scene.current?.setTerrain(state.terrain);
  }, [state?.terrain, sceneAttempt]);

  useEffect(() => {
    if (state) scene.current?.setLayerVisibility(state.layers);
  }, [state?.layers]);

  useEffect(() => {
    if (state) scene.current?.setEarthOpacity(state.earthOpacity);
  }, [state?.earthOpacity, sceneAttempt]);

  useEffect(() => {
    if (state) scene.current?.setOceanColor(state.oceanColor);
  }, [state?.oceanColor, sceneAttempt]);

  useEffect(() => {
    if (state)
      scene.current?.setCountryBorderStyle(
        state.countryBorderColor,
        state.countryBorderOpacity,
      );
  }, [state?.countryBorderColor, state?.countryBorderOpacity, sceneAttempt]);

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

  useEffect(() => {
    if (!selection) return;
    const dismissInspector = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      scene.current?.setSelection(null);
      setSelection(null);
    };
    window.addEventListener('keydown', dismissInspector);
    return () => window.removeEventListener('keydown', dismissInspector);
  }, [selection]);

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
                    paletteMode: 'metric-default',
                    surfacePalette: defaultPalette(metric),
                  }
                : current,
            )
          }
          onBasemap={(basemap) => update({ basemap })}
          onBasemapBrightness={(basemapBrightness) =>
            update({ basemapBrightness })
          }
          onBasemapOpacity={(basemapOpacity) => update({ basemapOpacity })}
          onCountryBorderColor={(countryBorderColor) =>
            update({ countryBorderColor })
          }
          onCountryBorderOpacity={(countryBorderOpacity) =>
            update({ countryBorderOpacity })
          }
          onDayNightLighting={(dayNightLighting) =>
            update({ dayNightLighting })
          }
          onTerrain={(terrain) => update({ terrain })}
          onSurfacePalette={(surfacePalette) =>
            update({ paletteMode: 'custom', surfacePalette })
          }
          onSurfaceOpacity={(surfaceOpacity) => update({ surfaceOpacity })}
          onEarthOpacity={(earthOpacity) => update({ earthOpacity })}
          onOceanColor={(oceanColor) => update({ oceanColor })}
          onSurfaceGeometry={(surfaceGeometry) => update({ surfaceGeometry })}
          onCellEdges={(cellEdges) => update({ cellEdges })}
          onEdgeColorMode={(edgeColorMode) => update({ edgeColorMode })}
          onEdgeFixedColor={(edgeFixedColor) => update({ edgeFixedColor })}
          onObservationShape={(observationShape) =>
            update({ observationShape })
          }
          onObservationColor={(observationColor) =>
            update({ observationColor })
          }
          onObservationGradient={(observationGradient) =>
            update({ observationGradient })
          }
          onObservationOpacity={(observationOpacity) =>
            update({ observationOpacity })
          }
          onObservationSize={(observationSize) => update({ observationSize })}
          onObservationRange={(observationSizeRange) =>
            update({ observationSizeRange })
          }
          onObservationSolidColor={(observationSolidColor) =>
            update({ observationSolidColor })
          }
          onSamplingAreas={(samplingAreas) => update({ samplingAreas })}
          onSamplingAreaColor={(samplingAreaColor) =>
            update({ samplingAreaColor })
          }
          onLayer={chooseLayer}
          onView={(view: ExplorerSceneMode) => update({ view })}
          onElevation={chooseElevation}
          onExaggeration={(exaggeration) => update({ exaggeration })}
          onHome={() => scene.current?.home(!reducedMotion)}
          onZoom={(direction) => scene.current?.zoom(direction)}
        />
      ) : (
        <aside className="atlas-controls atlas-controls--loading">
          <p className="atlas-kicker atlas-kicker--brand">
            <span className="brand-name">genomeOS</span> Atlas
          </p>
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
      {state && hover && (
        <HoverPreview
          colorEncoding={colorEncodingFor(hover.selection)}
          placeContext={placeContextFor(hover.selection)}
          position={hover.position}
          selection={hover.selection}
        />
      )}
      <div className="atlas-right-rail">
        {activeArtifact && selection && (
          <InspectorPanel
            artifact={activeArtifact}
            colorEncoding={colorEncodingFor(selection)}
            placeContext={placeContextFor(selection)}
            selection={selection}
            onClose={() => {
              scene.current?.setSelection(null);
              setSelection(null);
            }}
          />
        )}
        <div data-atlas-external-slot />
      </div>
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
