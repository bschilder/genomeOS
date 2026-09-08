/** Reviewed gnomAD and dbSNP evidence panel for Atlas design §11. */

import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { ArtifactRef, ExternalInfo } from '../../atlas/contracts';
import { downloadExternalInfo } from '../../atlas/external-info';
import { GnomadEvidence } from './GnomadEvidence';

type ExternalSource = 'gnomad' | 'dbsnp';

interface ExternalInfoPanelProps {
  artifact: ArtifactRef;
  load: (source: ExternalSource, signal: AbortSignal) => Promise<ExternalInfo>;
}

function sourceLabel(source: ExternalSource): string {
  return source === 'gnomad' ? 'gnomAD' : 'dbSNP';
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function DbsnpRecord({
  info,
}: {
  info: Extract<ExternalInfo, { source: 'dbsnp' }>;
}) {
  return (
    <>
      <section className="atlas-external-hero">
        <span>Reference SNP record</span>
        <h3>{info.record.rsid}</h3>
        <div className="atlas-external-badges">
          <span>{info.query.normalized_variant_id}</span>
          <span>{info.source_release}</span>
        </div>
      </section>

      <section className="atlas-external-section">
        <h3>Record summary</h3>
        <dl className="atlas-external-fields">
          <Field label="GRCh38 allele" value={info.record.hgvs} />
          <Field
            label="Citations"
            value={info.record.citation_count.toLocaleString()}
          />
          <Field label="Record updated" value={info.record.last_update_date} />
          <Field label="Queried rsID" value={info.query.rsid} />
        </dl>
      </section>

      <section className="atlas-external-section">
        <h3>SPDI representation</h3>
        <p className="atlas-external-section__intro">
          NCBI’s sequence-position-deletion-insertion representation uses a
          zero-based interbase position.
        </p>
        <dl className="atlas-external-fields">
          <Field label="Sequence accession" value={info.record.spdi.seq_id} />
          <Field
            label="Position (0-based)"
            value={info.record.spdi.position.toLocaleString()}
          />
          <Field
            label="Deleted sequence"
            value={info.record.spdi.deleted_sequence}
          />
          <Field
            label="Inserted sequence"
            value={info.record.spdi.inserted_sequence}
          />
        </dl>
      </section>

      <a
        className="atlas-external-source-link"
        href={info.record.source_url}
        target="_blank"
        rel="noreferrer"
      >
        Open this record in dbSNP <span aria-hidden="true">↗</span>
      </a>
    </>
  );
}

function SourceIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  );
}

function ExternalDetails({
  artifact,
  close,
  error,
  info,
  loading,
  lookup,
  source,
}: {
  artifact: ArtifactRef;
  close: () => void;
  error: string | null;
  info: ExternalInfo | null;
  loading: boolean;
  lookup: (source: ExternalSource) => void;
  source: ExternalSource;
}) {
  return (
    <aside
      className="atlas-external-details"
      aria-label="External variant information"
    >
      <header className="atlas-external-details__header">
        <span className="atlas-external-details__icon">
          <SourceIcon />
        </span>
        <div>
          <p className="atlas-kicker">External reference</p>
          <h2>Variant information</h2>
        </div>
        <button
          type="button"
          className="atlas-inspector__close"
          onClick={close}
          aria-label="Close external information"
        >
          ×
        </button>
      </header>

      <div
        className="atlas-external-tabs"
        role="group"
        aria-label="External data source"
      >
        {artifact.external_resources.map((resource) => (
          <button
            type="button"
            key={resource.source}
            aria-pressed={source === resource.source}
            onClick={() => lookup(resource.source)}
          >
            {sourceLabel(resource.source)}
          </button>
        ))}
      </div>

      <div className="atlas-external-details__scroll">
        {loading && (
          <p className="atlas-external-loading" role="status">
            Loading {sourceLabel(source)} information…
          </p>
        )}
        {error && (
          <p className="atlas-external-error" role="alert">
            {error}
          </p>
        )}
        {info?.source === 'gnomad' && <GnomadEvidence info={info} />}
        {info?.source === 'dbsnp' && <DbsnpRecord info={info} />}

        {info && (
          <section className="atlas-external-provenance">
            <h3>Data provenance</h3>
            <dl className="atlas-external-fields">
              <Field label="Source release" value={info.source_release} />
              <Field
                label="Retrieved from API"
                value={new Date(info.retrieved_at).toLocaleString(undefined, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}
              />
              <Field
                label="Cache schema"
                value={`Version ${info.schema_version}`}
              />
            </dl>
            <p>
              This reviewed response is cached so the Atlas remains reproducible
              and does not change silently when an external API changes.
            </p>
          </section>
        )}
      </div>

      {info && (
        <footer className="atlas-external-actions">
          <button type="button" onClick={() => downloadExternalInfo(info)}>
            Download displayed data
          </button>
        </footer>
      )}
    </aside>
  );
}

export function ExternalInfoPanel({ artifact, load }: ExternalInfoPanelProps) {
  const [source, setSource] = useState<ExternalSource | null>(null);
  const [info, setInfo] = useState<ExternalInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [portalTarget, setPortalTarget] = useState<Element | null>(null);
  const panelId = useId();
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    setPortalTarget(document.querySelector('[data-atlas-external-slot]'));
  }, []);

  useEffect(() => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setSource(null);
    setInfo(null);
    setError(null);
    setLoading(false);
    setOpen(false);
    return () => activeRequest.current?.abort();
  }, [artifact.id, artifact.model_version, artifact.data_version]);

  const close = () => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setLoading(false);
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [open]);

  const lookup = (next: ExternalSource) => {
    activeRequest.current?.abort();
    setSource(next);
    setInfo(null);
    setError(null);
    setLoading(true);
    const controller = new AbortController();
    activeRequest.current = controller;
    void load(next, controller.signal)
      .then((loaded) => {
        if (activeRequest.current === controller) setInfo(loaded);
      })
      .catch((caught) => {
        if (
          activeRequest.current !== controller ||
          (caught as Error).name === 'AbortError'
        )
          return;
        setError(
          caught instanceof Error
            ? caught.message
            : `${sourceLabel(next)} information could not be loaded.`,
        );
      })
      .finally(() => {
        if (activeRequest.current === controller) {
          activeRequest.current = null;
          setLoading(false);
        }
      });
  };

  const available = artifact.external_resources.length > 0;
  const toggle = () => {
    if (open) {
      close();
      return;
    }
    const next = source ?? artifact.external_resources[0]?.source;
    if (!next) return;
    setOpen(true);
    if (!info || info.source !== next) lookup(next);
  };

  return (
    <section className="atlas-external-info">
      <button
        type="button"
        className="atlas-external-info__button"
        aria-controls={panelId}
        aria-expanded={open}
        disabled={!available}
        onClick={toggle}
      >
        More info
      </button>
      {open &&
        available &&
        portalTarget &&
        source &&
        createPortal(
          <div id={panelId}>
            <ExternalDetails
              artifact={artifact}
              close={close}
              error={error}
              info={info}
              loading={loading}
              lookup={lookup}
              source={source}
            />
          </div>,
          portalTarget,
        )}
    </section>
  );
}
