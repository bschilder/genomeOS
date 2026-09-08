/** Loading, correction, and refusal states for Atlas design §11. */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import type { ContextStatus } from '../../atlas/scene/atlas-scene';
import type { ContextWarning } from '../../atlas/scene/context-controller';
import type {
  ExplorerActivity,
  ExplorerLoadStatus,
} from '../../atlas/progress';
import type { StateCorrection } from '../../atlas/url-state';

export type { ExplorerLoadStatus } from '../../atlas/progress';

interface AtlasStatusProps {
  status: ExplorerLoadStatus;
  activity: ExplorerActivity | null;
  contextStatus: ContextStatus;
  sceneWarnings: readonly ContextWarning[];
  corrections: StateCorrection[];
  error: string | null;
  webglFailed: boolean;
  onRetry: () => void;
}

function NavbarAtlasStatus({
  activity,
  status,
}: {
  activity: ExplorerActivity | null;
  status: ExplorerLoadStatus;
}) {
  const [target, setTarget] = useState<Element | null>(null);

  useEffect(() => {
    setTarget(document.querySelector('[data-atlas-status-slot]'));
  }, []);

  if (!target) return null;
  const ready = status === 'ready';
  const value =
    activity?.progress === null || activity?.progress === undefined
      ? null
      : Math.min(1, Math.max(0, activity.progress));
  const label = ready ? 'Atlas ready' : (activity?.label ?? status);
  return createPortal(
    <div className="atlas-status" role="status" aria-live="polite">
      <span
        className={`atlas-status__light atlas-status__light--${status.replace(' ', '-')}`}
      />
      <span className="atlas-status__copy">
        <strong>{label}</strong>
        {!ready && activity?.detail && <small>{activity.detail}</small>}
      </span>
      {!ready && activity && (
        <span
          className={`atlas-status__meter${value === null ? ' atlas-status__meter--indeterminate' : ''}`}
          role="progressbar"
          aria-label="Atlas operation progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={value === null ? undefined : Math.round(value * 100)}
          aria-valuetext={
            value === null
              ? 'Working'
              : `${Math.round(value * 100)} percent complete`
          }
        >
          <span
            style={value === null ? undefined : { width: `${value * 100}%` }}
          />
        </span>
      )}
    </div>,
    target,
  );
}

export function AtlasStatus({
  status,
  activity,
  contextStatus,
  sceneWarnings,
  corrections,
  error,
  webglFailed,
  onRetry,
}: AtlasStatusProps) {
  if (webglFailed) {
    return (
      <section className="atlas-failure" role="alert">
        <p className="atlas-kicker">Globe unavailable</p>
        <h2>This globe needs WebGL</h2>
        <p>
          Your browser could not start the graphics engine. Try enabling
          hardware acceleration or opening the explorer in a current browser. No
          scientific data was changed.
        </p>
        <div className="atlas-failure__actions">
          <button type="button" onClick={onRetry}>
            Retry globe
          </button>
          <a
            href="https://cesium.com/learn/cesiumjs-learn/cesiumjs-quickstart/#system-requirements"
            target="_blank"
            rel="noreferrer"
          >
            Browser requirements
          </a>
        </div>
      </section>
    );
  }

  const notices = [
    ...(contextStatus === 'fallback'
      ? ['Detailed map tiles are unavailable. Country outlines remain visible.']
      : []),
    ...sceneWarnings.map(({ message }) => message),
    ...(corrections.length > 0
      ? [
          `Corrected invalid link fields: ${corrections
            .map(({ field }) => field)
            .join(', ')}.`,
        ]
      : []),
  ];

  return (
    <>
      <NavbarAtlasStatus activity={activity} status={status} />
      {notices.length > 0 && (
        <p className="atlas-warning-banner" role="status">
          <strong>Notice:</strong> {notices.join(' · ')}
        </p>
      )}
      {error && (
        <div className="atlas-status-stack">
          <section className="atlas-error" role="alert">
            <strong>That map could not be displayed.</strong>
            <p>{error}</p>
            <button type="button" onClick={onRetry}>
              Retry data
            </button>
          </section>
        </div>
      )}
    </>
  );
}
