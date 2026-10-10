/** Complete client explorer and load state machine for Atlas design §11. */

import 'cesium/Build/Cesium/Widgets/widgets.css';
import '../../styles/atlas.css';

import { useEffect, useMemo, useRef, useState } from 'react';

import type { AtlasCatalog } from '../../atlas/contracts';
import { atlasWorker, bootAtlas } from '../../atlas/boot';
import { resolveElevationView } from '../../atlas/earth-style-catalog';
import {
  artifactVersion,
  displayKey,
  errorMessage,
  prefersReducedMotion,
  PUBLIC_SCENE_CAPABILITIES,
  REDUCED_MOTION_QUERY,
} from '../../atlas/explorer-runtime';
import {
  observationColorEncoding,
  observationDomains,
  type ObservationColorEncoding,
} from '../../atlas/observation-encoding';
import {
  nearestPlaceContext,
  type ObservationPlaceContext,
} from '../../atlas/place-context';
import { aggregateTransferProgress } from '../../atlas/progress';
import type {
  AtlasSceneController,
  ContextStatus,
  SceneCapabilities,
  SceneProgressListener,
} from '../../atlas/scene/atlas-scene';
import type { ContextWarning } from '../../atlas/scene/context-controller';
import { applySceneStyle, observationStyleFor } from '../../atlas/scene-style';
import {
  parseExplorerState,
  serializeExplorerState,
  type ExplorerSceneMode,
  type ExplorerState,
  type LayerId,
  type StateCorrection,
} from '../../atlas/url-state';
import { defaultPalette, type Metric } from '../../atlas/visual-encoding';
import { AtlasDataCredit } from './AtlasDataCredit';
import { AtlasLegend } from './AtlasLegend';
import { AtlasStatus } from './AtlasStatus';
import { ExplorerControls } from './ExplorerControls';
import { ControlsLoading } from './ExplorerHeading';
import { HoverPreview } from './HoverPreview';
import { InspectorPanel, type InspectorSelection } from './InspectorPanel';
import { PanelSheet } from './PanelSheet';
import { useArtifactPipeline } from './useArtifactPipeline';
import { nextPaint, useAtlasActivity } from './useAtlasActivity';
import { EscapeStackProvider } from './useEscapeStack';
import { ExplorerPanelsProvider } from './useExplorerPanels';
import { useObservationPlaces } from './useObservationPlaces';
import { useAtlasSceneLifecycle } from './useAtlasSceneLifecycle';
import {
  useAtlasDataProvider,
  useContextSourceUrls,
} from './useAtlasDataProvider';
import type { SceneFailure } from './useAtlasSceneLifecycle';

interface AtlasExplorerProps {
  artifactDataBase: string;
  cesiumToken?: string;
  siteDataBase: string;
}

// Island module evaluation (before React mounts) starts the data worker and the Cesium chunk.
bootAtlas();

/**
 * A restyle before anything is displayed rebuilds the pending cold request, and the pipeline's
 * `setArtifact` for that request settles with the rebuild (ScientificLayers.setArtifact), so the
 * pipeline reports its outcome; this copy is only marked handled.
 */
function restyleColdLoad(restyle: Promise<void> | undefined): void {
  restyle?.catch(() => undefined);
}

export default function AtlasExplorer({
  artifactDataBase,
  cesiumToken = '',
  siteDataBase,
}: AtlasExplorerProps) {
  const provider = useAtlasDataProvider(artifactDataBase, siteDataBase);
  const sceneElement = useRef<HTMLDivElement>(null);
  const scene = useRef<AtlasSceneController | null>(null);
  const cameraApplied = useRef(false);
  const appliedDisplay = useRef<string | null>(null);
  const [sceneAttempt, setSceneAttempt] = useState(0);
  const [sceneController, setSceneController] =
    useState<AtlasSceneController | null>(null);
  const [dataAttempt, setDataAttempt] = useState(0);
  const [catalog, setCatalog] = useState<AtlasCatalog | null>(null);
  const contextUrls = useContextSourceUrls(provider, catalog);
  const [state, setState] = useState<ExplorerState | null>(null);
  const [selection, setSelection] = useState<InspectorSelection | null>(null);
  const [hover, setHover] = useState<{
    position: { x: number; y: number };
    selection: InspectorSelection;
  } | null>(null);
  const [contextStatus, setContextStatus] = useState<ContextStatus>('loading');
  const [sceneWarnings, setSceneWarnings] = useState<readonly ContextWarning[]>(
    [],
  );
  const [capabilities, setCapabilities] = useState<SceneCapabilities>(
    PUBLIC_SCENE_CAPABILITIES,
  );
  const [corrections, setCorrections] = useState<StateCorrection[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sceneFailure, setSceneFailure] = useState<SceneFailure | null>(null);
  // A data worker that died (its module script failed to download on a flaky link, or it threw)
  // fails every later request, and only a new page starts a new one, so it shows the reload panel
  // rather than a "Retry data" that cannot succeed (final review spec-3). Kept apart from
  // sceneFailure, which every new scene resets.
  const [workerCrashed, setWorkerCrashed] = useState(false);
  const failure: SceneFailure | null =
    sceneFailure ?? (workerCrashed ? 'download' : null);
  const [viewNotice, setViewNotice] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion);
  const [explorerNode, setExplorerNode] = useState<HTMLDivElement | null>(null);
  const [topSlot, setTopSlot] = useState<HTMLDivElement | null>(null);
  const {
    activity,
    begin: beginActivity,
    fail: failActivity,
    finish: finishActivity,
    runScene: runSceneActivity,
    status,
    update: updateActivity,
  } = useAtlasActivity(scene, (caught) => setError(errorMessage(caught)));
  const pipeline = useArtifactPipeline({
    activity: {
      begin: beginActivity,
      fail: failActivity,
      finish: finishActivity,
      update: updateActivity,
    },
    appliedDisplay,
    cameraApplied,
    catalog,
    // #417's early return on a failed scene: nothing more is streamed into a stopped or missing
    // globe while the failure panel is up (final review spec-8).
    controller: failure ? null : sceneController,
    dataAttempt,
    onArtifactChange: () => {
      scene.current?.setSelection(null);
      setSelection(null);
      setHover(null);
    },
    provider,
    reducedMotion,
    setError,
    state,
  });
  const activeArtifact = pipeline.displayed?.ref ?? null;
  const pickTarget = pipeline.displayed ?? pipeline.revealing;
  const inspectorArtifact = activeArtifact ?? pickTarget?.ref ?? null;
  const legendArtifact =
    activeArtifact ??
    (pipeline.revealLegend ? (pipeline.revealing?.ref ?? null) : null);
  const sceneHasArtifact = () =>
    Boolean(activeArtifact && scene.current?.displayedLayer());
  const activeObservations = pipeline.displayed?.observations ?? null;
  const activeObservationDomains = useMemo(
    () =>
      activeObservations && activeObservations.observations.length > 0
        ? observationDomains(activeObservations.observations)
        : null,
    [activeObservations],
  );
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
  const wantsPlaceContext =
    hover?.selection.kind === 'observation' ||
    selection?.kind === 'observation';
  const placeCatalog = useObservationPlaces(
    contextUrls?.places ?? null,
    wantsPlaceContext,
  );
  const placeContextFor = (
    candidate: InspectorSelection | null,
  ): ObservationPlaceContext | null => {
    if (!placeCatalog || !candidate || candidate.kind !== 'observation')
      return null;
    return nearestPlaceContext(candidate.value, placeCatalog);
  };
  useEffect(() => atlasWorker().onCrash(() => setWorkerCrashed(true)), []);

  useEffect(() => {
    const media = window.matchMedia(REDUCED_MOTION_QUERY);
    const updatePreference = () => setReducedMotion(media.matches);
    updatePreference();
    media.addEventListener('change', updatePreference);
    return () => media.removeEventListener('change', updatePreference);
  }, []);

  const sceneGeneration = useAtlasSceneLifecycle({
    attempt: sceneAttempt,
    bind: (controller) => {
      setSceneController(controller);
      setCapabilities(controller.capabilities());
      const removePick = controller.onPick((pick) => {
        const target = pipeline.targetRef.current;
        if (pick?.kind === 'surface') {
          setSelection(
            target?.artifactKey === pick.artifactKey
              ? {
                  artifactKey: pick.artifactKey,
                  kind: 'surface',
                  row: pick.row,
                }
              : null,
          );
        } else if (pick?.kind === 'observation') {
          const value =
            target?.artifactKey === pick.artifactKey
              ? target.observationMap.get(pick.sourceRecordId)
              : undefined;
          setSelection(value ? { kind: 'observation', value } : null);
        } else setSelection(null);
      });
      const removeHover = controller.onHover((hovered) => {
        const target = pipeline.targetRef.current;
        const pick = hovered?.pick;
        if (
          hovered &&
          pick?.kind === 'surface' &&
          target?.artifactKey === pick.artifactKey
        ) {
          setHover({
            position: hovered.screenPosition,
            selection: {
              artifactKey: pick.artifactKey,
              kind: 'surface',
              row: pick.row,
            },
          });
        } else if (
          hovered &&
          pick?.kind === 'observation' &&
          target?.artifactKey === pick.artifactKey
        ) {
          const value = target.observationMap.get(pick.sourceRecordId);
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
      const removeRenderError = controller.onRenderError(() =>
        setSceneFailure('render'),
      );
      return () => {
        setSceneController(null);
        removePick();
        removeHover();
        removeCamera();
        removeContext();
        removeWarnings();
        removeRenderError();
      };
    },
    cesiumToken,
    element: sceneElement,
    markTarget: explorerNode,
    naturalEarthUrl: contextUrls?.borders ?? null,
    onReset: () => {
      cameraApplied.current = false;
      appliedDisplay.current = null;
      setSceneFailure(null);
    },
    onUnavailable: setSceneFailure,
    reducedMotion,
    scene,
    worker: atlasWorker(),
  });

  useEffect(() => {
    // A new scene (first load or "Retry globe") receives the whole current style at once; the
    // per-field effects below then handle later changes (fast-load design §B.6.11).
    if (scene.current && state) applySceneStyle(scene.current, state);
  }, [sceneGeneration]);

  useEffect(() => {
    if (!provider) return;
    const controller = new AbortController();
    const sequence = beginActivity('loading catalog', {
      detail: 'Waiting for the catalog response',
      label: 'Loading catalog',
      progress: null,
    });
    setError(null);
    provider
      .getCatalog(controller.signal, (transfer) => {
        updateActivity(sequence, {
          detail: 'Downloading the public map catalog',
          label: 'Loading catalog',
          progress: aggregateTransferProgress([transfer]),
        });
      })
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
        if ((caught as Error).name !== 'AbortError') {
          failActivity(sequence);
          setError(errorMessage(caught));
        }
      });
    return () => controller.abort();
  }, [provider, dataAttempt]);

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
    if (!state) return;
    if (!sceneHasArtifact()) {
      restyleColdLoad(scene.current?.setMetric(state.metric));
      return;
    }
    return runSceneActivity(
      'Updating inferred surface',
      'Changing the displayed metric',
      (controller, progress) => controller.setMetric(state.metric, progress),
    );
  }, [state?.metric, sceneController]);

  useEffect(() => {
    if (!state) return;
    const apply = (
      controller: AtlasSceneController,
      progress?: SceneProgressListener,
    ) =>
      controller.setSurfaceStyle(
        state.surfacePalette,
        state.surfaceOpacity,
        state.cellEdges,
        state.edgeColorMode,
        state.edgeFixedColor,
        state.surfaceGeometry,
        progress,
      );
    if (!sceneHasArtifact()) {
      restyleColdLoad(scene.current ? apply(scene.current) : undefined);
      return;
    }
    return runSceneActivity(
      'Updating inferred surface',
      'Applying the selected surface geometry',
      (controller, progress) => apply(controller, progress),
    );
  }, [
    state?.surfacePalette,
    state?.surfaceOpacity,
    state?.cellEdges,
    state?.edgeColorMode,
    state?.edgeFixedColor,
    state?.surfaceGeometry,
    sceneController,
  ]);

  useEffect(() => {
    if (!state) return;
    const style = observationStyleFor(state);
    if (!sceneHasArtifact()) {
      restyleColdLoad(scene.current?.setObservationStyle(style));
      return;
    }
    return runSceneActivity(
      'Updating measured points',
      'Applying the selected marker encoding',
      (controller, progress) => controller.setObservationStyle(style, progress),
    );
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
    sceneController,
  ]);

  useEffect(() => {
    if (!state) return;
    if (!sceneHasArtifact()) {
      void scene.current?.setBasemap(state.basemap);
      return;
    }
    return runSceneActivity(
      'Changing basemap',
      'Waiting for imagery services',
      (controller) => controller.setBasemap(state.basemap),
    );
  }, [state?.basemap, sceneAttempt, sceneController]);

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
    sceneController,
  ]);

  useEffect(() => {
    if (!state) return;
    if (!sceneHasArtifact()) {
      void scene.current?.setTerrain(state.terrain);
      return;
    }
    return runSceneActivity(
      'Changing terrain',
      'Waiting for terrain services',
      (controller) => controller.setTerrain(state.terrain),
    );
  }, [state?.terrain, sceneAttempt, sceneController]);

  useEffect(() => {
    if (state) scene.current?.setLayerVisibility(state.layers);
  }, [state?.layers, sceneController]);

  useEffect(() => {
    if (state) scene.current?.setEarthOpacity(state.earthOpacity);
  }, [state?.earthOpacity, sceneAttempt, sceneController]);

  useEffect(() => {
    if (state) scene.current?.setOceanColor(state.oceanColor);
  }, [state?.oceanColor, sceneAttempt, sceneController]);

  useEffect(() => {
    if (state)
      scene.current?.setCountryBorderStyle(
        state.countryBorderColor,
        state.countryBorderOpacity,
      );
  }, [
    state?.countryBorderColor,
    state?.countryBorderOpacity,
    sceneAttempt,
    sceneController,
  ]);

  useEffect(() => {
    if (!state || !activeArtifact || !scene.current) return;
    const key = displayKey(state, reducedMotion);
    if (appliedDisplay.current === key) return;
    const controller = scene.current;
    let canceled = false;
    const activityId = beginActivity('rendering', {
      detail: 'Reprojecting scientific layers',
      label: 'Updating map view',
      progress: null,
    });
    void (async () => {
      try {
        await nextPaint();
        if (canceled || controller !== scene.current) return;
        await controller.setSceneMode(state.view, reducedMotion);
        if (canceled || controller !== scene.current) return;
        await controller.setElevation(state.elevation, state.exaggeration);
        if (canceled || controller !== scene.current) return;
        appliedDisplay.current = key;
        finishActivity(activityId);
      } catch (caught) {
        if (!canceled) {
          failActivity(activityId);
          setError(errorMessage(caught));
        }
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
    <EscapeStackProvider>
      <ExplorerPanelsProvider>
        <div
          className="atlas-explorer"
          data-atlas-explorer="AtlasExplorer"
          data-atlas-active={activeArtifact?.id ?? ''}
          data-atlas-ready={status === 'ready' && !failure ? 'true' : 'false'}
          role="application"
          aria-label="genomeOS globe explorer"
          ref={setExplorerNode}
        >
          <div className="atlas-top-slot" ref={setTopSlot} />
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
              artifactDataBase={artifactDataBase}
              state={state}
              disabled={false}
              explorer={explorerNode}
              topSlot={topSlot}
              onEntity={chooseEntity}
              onExternalInfo={(source, signal) => {
                const selected = catalog.artifacts.find(
                  (artifact) => artifact.id === state.entityId,
                );
                if (
                  !provider ||
                  !selected ||
                  activeArtifact?.id !== selected.id
                )
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
              onSurfaceGeometry={(value) => update({ surfaceGeometry: value })}
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
              onObservationSize={(value) => update({ observationSize: value })}
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
            <ControlsLoading />
          )}

          <AtlasStatus
            status={status}
            activity={activity}
            contextStatus={contextStatus}
            sceneWarnings={sceneWarnings}
            corrections={corrections}
            error={error}
            sceneFailure={failure}
            onRetry={() => {
              // A new scene reuses Cesium's shared workers and their failed imports, a failed
              // scene chunk stays failed in this document, and so does a dead data worker
              // ('download'); reload instead.
              if (failure === 'render' || failure === 'download')
                window.location.reload();
              else if (failure) setSceneAttempt((value) => value + 1);
              else setDataAttempt((value) => value + 1);
            }}
          />
          {viewNotice && (
            <p className="atlas-view-notice" role="status">
              {viewNotice}
            </p>
          )}
          {legendArtifact && state && (
            <AtlasLegend
              artifact={legendArtifact}
              layer={activeArtifact ? pipeline.legendLayer : null}
              loading={!activeArtifact}
              state={state}
            />
          )}
          {state && hover && (
            <HoverPreview
              colorEncoding={colorEncodingFor(hover.selection)}
              detail={pipeline.detailStatus}
              placeContext={placeContextFor(hover.selection)}
              position={hover.position}
              selection={hover.selection}
              surface={pickTarget?.surface ?? null}
            />
          )}
          <PanelSheet explorer={explorerNode}>
            {inspectorArtifact && selection && (
              <InspectorPanel
                artifact={inspectorArtifact}
                colorEncoding={colorEncodingFor(selection)}
                detail={pipeline.detailStatus}
                placeContext={placeContextFor(selection)}
                selection={selection}
                surface={pickTarget?.surface ?? null}
                onClose={() => {
                  scene.current?.setSelection(null);
                  setSelection(null);
                }}
                onRetryDetail={pipeline.retryDetail}
              />
            )}
          </PanelSheet>
          <AtlasDataCredit />
        </div>
      </ExplorerPanelsProvider>
    </EscapeStackProvider>
  );
}
