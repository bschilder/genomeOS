/** Loading, correction, and refusal states for Atlas design §11. */

import type { ContextStatus } from '../../atlas/scene/atlas-scene';
import type { ContextWarning } from '../../atlas/scene/context-controller';
import type { StateCorrection } from '../../atlas/url-state';

export type ExplorerLoadStatus =
  'loading catalog' | 'loading artifact' | 'validating' | 'rendering' | 'ready';

interface AtlasStatusProps {
  status: ExplorerLoadStatus;
  contextStatus: ContextStatus;
  sceneWarnings: readonly ContextWarning[];
  corrections: StateCorrection[];
  error: string | null;
  webglFailed: boolean;
  onRetry: () => void;
}

export function AtlasStatus({
  status,
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
      {notices.length > 0 && (
        <p className="atlas-warning-banner" role="status">
          <strong>Notice:</strong> {notices.join(' · ')}
        </p>
      )}
      <div className="atlas-status-stack">
        <p className="atlas-status" aria-live="polite">
          <span
            className={`atlas-status__light atlas-status__light--${status.replace(' ', '-')}`}
          />
          {status === 'ready' ? 'Atlas ready' : status}
        </p>
        {error && (
          <section className="atlas-error" role="alert">
            <strong>That map could not be displayed.</strong>
            <p>{error}</p>
            <button type="button" onClick={onRetry}>
              Retry data
            </button>
          </section>
        )}
      </div>
    </>
  );
}
