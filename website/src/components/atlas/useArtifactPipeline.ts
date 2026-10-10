/** Artifact fetch, scene handoff, commit and detail-tier lifecycle for Atlas design §11
 * (spec 2026-10-07 §B.2, §B.6.2, §B.6.8, §B.6.12).
 *
 * Downloads start as soon as the catalog and URL state exist, independent of
 * the scene. The scene receives promises, so observations can appear before
 * the surface. The displayed artifact changes only at the scene's commit, and
 * the f64 detail tier is fetched after `atlas:surface-visible`.
 *
 * Marks describe the scene's current epoch, so they are read against the
 * request last handed to the scene, never a newer one still on its way. A
 * detail tier belongs to its artifact: the commit that leaves an artifact
 * aborts its request, and an outcome for an artifact that is neither displayed
 * nor requested changes nothing.
 */

import { useEffect, useRef, useState } from 'react';

import type { AtlasCatalog, ObservationArtifact } from '../../atlas/contracts';
import {
  artifactVersion,
  displayKey,
  errorMessage,
} from '../../atlas/explorer-runtime';
import {
  createTransferProgressTracker,
  type ExplorerActivity,
  type ExplorerLoadStatus,
} from '../../atlas/progress';
import type {
  ArtifactSceneApi,
  AtlasSceneController,
  DisplayedLayer,
} from '../../atlas/scene/types';
import type { StaticAtlasDataProvider } from '../../atlas/static-provider';
import {
  artifactKeyFor,
  type SurfaceArtifact,
} from '../../atlas/surface-columns';
import type { ExplorerState } from '../../atlas/url-state';
import {
  attachObservations,
  classifyDetailFailure,
  createLoadedArtifact,
  detailStatusFor,
  withoutKey,
  type DetailFailure,
  type LoadedArtifact,
} from './artifact-pipeline';
import type { DetailStatus } from './surface-cell-view';
import { nextPaint } from './useAtlasActivity';

type PipelineController = ArtifactSceneApi &
  Pick<
    AtlasSceneController,
    'setCamera' | 'setElevation' | 'setSceneMode' | 'setSelection'
  >;
type PipelineProvider = Pick<
  StaticAtlasDataProvider,
  'getObservations' | 'getSurface' | 'getSurfaceDetail'
>;

interface PipelineActivity {
  begin(
    status: Exclude<ExplorerLoadStatus, 'ready'>,
    activity: ExplorerActivity,
  ): number;
  update(id: number, activity: ExplorerActivity): void;
  finish(id: number): void;
  fail(id: number): void;
}

interface ArtifactRequest {
  sequence: number;
  entry: LoadedArtifact;
  observations: Promise<ObservationArtifact | null>;
  surface: Promise<SurfaceArtifact>;
}

export interface ArtifactPipelineOptions {
  activity: PipelineActivity;
  appliedDisplay: { current: string | null };
  cameraApplied: { current: boolean };
  catalog: AtlasCatalog | null;
  controller: PipelineController | null;
  dataAttempt: number;
  onArtifactChange: () => void;
  /** Null during server rendering: the inline catalog and the worker exist only in the browser. */
  provider: PipelineProvider | null;
  reducedMotion: boolean;
  setError: (message: string | null) => void;
  state: ExplorerState | null;
}

export interface ArtifactPipeline {
  /** The committed artifact: what the scene shows and the legend describes. */
  displayed: LoadedArtifact | null;
  /** The artifact being revealed on a cold load, before its commit. */
  revealing: LoadedArtifact | null;
  revealLegend: boolean;
  legendLayer: DisplayedLayer | null;
  detailStatus: DetailStatus;
  retryDetail: () => void;
  /** Displayed, else revealing: the only artifact whose picks may select. */
  targetRef: { readonly current: LoadedArtifact | null };
}

export function useArtifactPipeline(
  options: ArtifactPipelineOptions,
): ArtifactPipeline {
  const latest = useRef(options);
  latest.current = options;
  const requestSequence = useRef(0);
  const activityId = useRef(0);
  const entries = useRef(new Map<string, LoadedArtifact>());
  const latestRequest = useRef<ArtifactRequest | null>(null);
  /** The artifact last handed to the scene: the one its marks describe. */
  const sceneEntry = useRef<LoadedArtifact | null>(null);
  const displayedRef = useRef<LoadedArtifact | null>(null);
  const targetRef = useRef<LoadedArtifact | null>(null);
  const detailRequests = useRef(new Map<string, AbortController>());
  const [request, setRequest] = useState<ArtifactRequest | null>(null);
  const [displayed, setDisplayed] = useState<LoadedArtifact | null>(null);
  const [revealing, setRevealing] = useState<LoadedArtifact | null>(null);
  const [revealLegend, setRevealLegend] = useState(false);
  const [legendLayer, setLegendLayer] = useState<DisplayedLayer | null>(null);
  const [failures, setFailures] = useState<
    Readonly<Record<string, DetailFailure>>
  >({});
  const [, setDetailVersion] = useState(0);
  const { catalog, controller, dataAttempt, provider, reducedMotion, state } =
    options;

  /** Displayed, or still requested: the artifacts a detail outcome may report on. */
  const isCurrent = (key: string): boolean =>
    displayedRef.current?.artifactKey === key ||
    latestRequest.current?.entry.artifactKey === key;

  const loadDetail = (entry: LoadedArtifact): void => {
    const surface = entry.surface;
    const key = entry.artifactKey;
    const detailProvider = latest.current.provider;
    if (!detailProvider || !surface) return;
    if (surface.detail) {
      // Attached under an earlier scene (the provider keeps each surface); this scene's
      // values-ready mark still needs it.
      latest.current.controller?.markValuesReady(key);
      return;
    }
    if (detailRequests.current.has(key)) return;
    const abort = new AbortController();
    detailRequests.current.set(key, abort);
    setFailures((current) => withoutKey(current, key));
    // A request aborted at a commit may settle after a newer one for the same key started.
    const release = () => {
      if (detailRequests.current.get(key) === abort)
        detailRequests.current.delete(key);
    };
    detailProvider
      .getSurfaceDetail(entry.ref, abort.signal)
      .then(() => {
        release();
        setDetailVersion((version) => version + 1);
        latest.current.controller?.markValuesReady(key);
      })
      .catch((caught: unknown) => {
        release();
        const failure = classifyDetailFailure(caught);
        if (failure === 'aborted' || abort.signal.aborted || !isCurrent(key))
          return;
        setFailures((current) => ({ ...current, [key]: failure }));
        if (failure !== 'invalid') return;
        // Task 66 ruling: remove and announce only the artifact picks resolve to that is also the
        // one requested. During an A→B switch A stays displayed until B's commit; acting on A's
        // late failure then would put A's error over B and take over B's activity, so
        // data-atlas-ready would stay "false" on a healthy B. A recorded failure is cleared when
        // the artifact is shown again (its surface-visible starts a fresh loadDetail).
        if (
          targetRef.current?.artifactKey !== key ||
          latestRequest.current?.entry.artifactKey !== key
        )
          return;
        const {
          activity,
          controller: scene,
          onArtifactChange,
          setError,
        } = latest.current;
        scene?.removeSurface(key);
        onArtifactChange();
        setError(`${entry.ref.id}: ${errorMessage(caught)}`);
        activity.fail(
          activity.begin('loading artifact', {
            detail: 'Cell values failed validation',
            label: `Loading ${entry.ref.label}`,
            progress: null,
          }),
        );
      });
  };

  useEffect(() => {
    if (!provider || !catalog || !state) return;
    const { activity, setError } = latest.current;
    const ref = catalog.artifacts.find(
      (candidate) => candidate.id === state.entityId,
    );
    if (!ref || artifactVersion(ref) !== state.artifactVersion) {
      setError(
        `The requested map “${state.entityId}” at version “${state.artifactVersion || 'unspecified'}” is unavailable. Choose an available map to continue.`,
      );
      return;
    }
    const abort = new AbortController();
    const sequence = ++requestSequence.current;
    const artifactKey = artifactKeyFor(ref);
    activityId.current = activity.begin('loading artifact', {
      detail: 'Waiting for scientific artifact responses',
      label: `Loading ${ref.label}`,
      progress: null,
    });
    const report = createTransferProgressTracker<'observations' | 'surface'>(
      ref.observations_available ? ['surface', 'observations'] : ['surface'],
      (progress) => {
        if (sequence !== requestSequence.current) return;
        latest.current.activity.update(activityId.current, {
          detail: 'Downloading surface and measured observations',
          label: `Loading ${ref.label}`,
          progress,
        });
      },
    );
    setError(null);
    const entry = createLoadedArtifact(artifactKey, ref);
    const observations = provider
      .getObservations(ref, abort.signal, report('observations'))
      .then((loaded) => {
        attachObservations(entry, loaded);
        return loaded;
      });
    const surface = provider
      .getSurface(ref, abort.signal, report('surface'))
      .then((loaded) => {
        entry.surface = loaded;
        return loaded;
      });
    // The scene reports these failures; keep the unawaited copies quiet.
    observations.catch(() => undefined);
    surface.catch(() => undefined);
    entries.current.set(artifactKey, entry);
    const next: ArtifactRequest = { entry, observations, sequence, surface };
    latestRequest.current = next;
    setRequest(next);
    return () => abort.abort();
  }, [catalog, provider, state?.entityId, state?.artifactVersion, dataAttempt]);

  useEffect(() => {
    sceneEntry.current = null;
    displayedRef.current = null;
    targetRef.current = null;
    setDisplayed(null);
    setRevealing(null);
    setRevealLegend(false);
    setLegendLayer(null);
    if (!controller) return;
    const removeCommit = controller.onCommit((artifactKey) => {
      const entry = entries.current.get(artifactKey) ?? null;
      if (targetRef.current?.artifactKey !== artifactKey)
        latest.current.onArtifactChange();
      displayedRef.current = entry;
      targetRef.current = entry;
      setDisplayed(entry);
      setRevealing(null);
      setRevealLegend(false);
      setLegendLayer(controller.displayedLayer());
      const keep = new Set([
        artifactKey,
        latestRequest.current?.entry.artifactKey,
      ]);
      for (const key of [...entries.current.keys()])
        if (!keep.has(key)) entries.current.delete(key);
      // A left artifact's detail tier is neither awaited nor reported.
      for (const [key, abort] of [...detailRequests.current])
        if (!keep.has(key)) {
          detailRequests.current.delete(key);
          abort.abort();
        }
      setFailures((current) => {
        let next = current;
        for (const key of Object.keys(current))
          if (!keep.has(key)) next = withoutKey(next, key);
        return next;
      });
    });
    const removeMark = controller.onMark((mark) => {
      const entry = sceneEntry.current;
      if (!entry) return;
      if (
        (mark === 'observations-visible' || mark === 'surface-first-chunk') &&
        displayedRef.current === null
      ) {
        targetRef.current = entry;
        setRevealing(entry);
        if (mark === 'surface-first-chunk') setRevealLegend(true);
      }
      if (mark === 'surface-visible') loadDetail(entry);
    });
    return () => {
      removeCommit();
      removeMark();
    };
  }, [controller]);

  useEffect(() => {
    const current = latest.current.state;
    if (!request || !controller || !current) return;
    let canceled = false;
    const live = () =>
      !canceled && request.sequence === requestSequence.current;
    const { ref } = request.entry;
    const id = latest.current.activity.begin('loading artifact', {
      detail: 'Waiting for scientific artifact responses',
      label: `Loading ${ref.label}`,
      progress: null,
    });
    activityId.current = id;
    void (async () => {
      await nextPaint();
      if (!live()) return;
      await controller.setSceneMode(current.view, reducedMotion);
      if (!live()) return;
      await controller.setElevation(current.elevation, current.exaggeration);
      if (!live()) return;
      latest.current.appliedDisplay.current = displayKey(
        current,
        reducedMotion,
      );
      // The scene begins this request's epoch now: a cold reveal of another artifact ends.
      if (
        displayedRef.current === null &&
        sceneEntry.current !== request.entry
      ) {
        targetRef.current = null;
        setRevealing(null);
        setRevealLegend(false);
      }
      sceneEntry.current = request.entry;
      try {
        await controller.setArtifact(
          {
            artifactId: ref.id,
            artifactKey: request.entry.artifactKey,
            lookAt: latest.current.cameraApplied.current
              ? undefined
              : { lat: current.camera.lat, lon: current.camera.lon },
            observations: request.observations,
            surface: request.surface,
          },
          (progress) => {
            if (!live()) return;
            latest.current.activity.update(id, {
              detail: progress.detail,
              label: `Rendering ${ref.label}`,
              progress: progress.progress,
            });
          },
        );
      } catch (caught) {
        // After a failed request the scene rebuilds the displayed artifact (Task 62's fallback).
        // A cancelled handoff's scene is gone or has a newer request; it decides nothing here.
        if (!canceled && sceneEntry.current === request.entry)
          sceneEntry.current = displayedRef.current;
        throw caught;
      }
      if (!live()) return;
      if (!latest.current.cameraApplied.current) {
        controller.setCamera(
          latest.current.state?.camera ?? current.camera,
          !reducedMotion,
        );
        latest.current.cameraApplied.current = true;
      }
      latest.current.activity.finish(id);
    })().catch((caught: unknown) => {
      if (!live() || (caught as Error).name === 'AbortError') return;
      latest.current.activity.fail(id);
      latest.current.setError(`${ref.id}: ${errorMessage(caught)}`);
    });
    return () => {
      canceled = true;
    };
  }, [request, controller, reducedMotion]);

  useEffect(
    () => () => {
      for (const abort of detailRequests.current.values()) abort.abort();
    },
    [],
  );

  const target = displayed ?? revealing;
  return {
    detailStatus: detailStatusFor(
      target?.surface ?? null,
      target ? failures[target.artifactKey] : undefined,
    ),
    displayed,
    legendLayer,
    retryDetail: () => {
      const entry = targetRef.current;
      if (entry) loadDetail(entry);
    },
    revealLegend,
    revealing,
    targetRef,
  };
}
