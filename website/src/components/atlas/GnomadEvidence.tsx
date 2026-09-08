/** Layered gnomAD context navigator for Atlas design §11. */

import { useState, type CSSProperties, type ReactNode } from 'react';

import type { ExternalInfo } from '../../atlas/contracts';
import '../../styles/gnomad-evidence.css';
import { GnomadEvidenceOverview } from './GnomadEvidenceOverview';

type GnomadInfo = Extract<ExternalInfo, { source: 'gnomad' }>;
type GnomadRecord = GnomadInfo['record'];
type GnomadView = 'ancestry' | 'clinvar' | 'constraint' | 'overview';

function percent(value: number): string {
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 4 })}%`;
}

function decimal(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function EvidenceChoice({
  detail,
  label,
  readout,
  select,
}: {
  detail: string;
  label: string;
  readout: string;
  select: () => void;
}) {
  return (
    <button type="button" className="atlas-gnomad-choice" onClick={select}>
      <span className="atlas-gnomad-choice__readout" aria-hidden="true">
        {readout}
      </span>
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
    </button>
  );
}

function EvidenceIndex({
  record,
  select,
}: {
  record: GnomadRecord;
  select: (view: GnomadView) => void;
}) {
  const ancestryCount = record.genetic_ancestry_group_frequencies.length;
  const conditionCount = record.clinvar?.conditions.length ?? 0;
  return (
    <section className="atlas-external-section atlas-gnomad-index">
      <div>
        <h3>Explore gnomAD evidence</h3>
        <p>Open one focused view without losing the variant context.</p>
      </div>
      <div className="atlas-gnomad-index__choices">
        <EvidenceChoice
          detail={`${ancestryCount} ${ancestryCount === 1 ? 'group' : 'groups'}`}
          label="Genetic ancestry"
          readout={ancestryCount.toLocaleString()}
          select={() => select('ancestry')}
        />
        <EvidenceChoice
          detail={record.genomic_constraint ? '1 kb region' : 'Unavailable'}
          label="Genomic constraint"
          readout={record.genomic_constraint?.z.toFixed(2) ?? '—'}
          select={() => select('constraint')}
        />
        <EvidenceChoice
          detail={`${conditionCount} ${conditionCount === 1 ? 'condition' : 'conditions'}`}
          label="ClinVar"
          readout={conditionCount.toLocaleString()}
          select={() => select('clinvar')}
        />
      </div>
    </section>
  );
}

function DetailHeader({
  children,
  title,
  toOverview,
}: {
  children: ReactNode;
  title: string;
  toOverview: () => void;
}) {
  return (
    <>
      <button type="button" className="atlas-gnomad-back" onClick={toOverview}>
        <span aria-hidden="true">‹</span> Back to variant overview
      </button>
      <section className="atlas-gnomad-detail">
        <header>
          <h3>{title}</h3>
        </header>
        <div className="atlas-gnomad-detail__body">{children}</div>
      </section>
    </>
  );
}

function AncestryView({ record, toOverview }: DetailProps) {
  const rows = [...record.genetic_ancestry_group_frequencies].sort(
    (first, second) =>
      second.af - first.af || first.label.localeCompare(second.label),
  );
  const maximum = Math.max(0, ...rows.map(({ af }) => af));
  return (
    <DetailHeader
      title="Genetic ancestry group frequencies"
      toOverview={toOverview}
    >
      <p>
        These are broad aggregate genetic-ancestry labels used by gnomAD. They
        are not geographic populations or individual identities.
      </p>
      {rows.length ? (
        <div className="atlas-gnomad-table-wrap">
          <table className="atlas-gnomad-table">
            <thead>
              <tr>
                <th scope="col">Group</th>
                <th scope="col">Frequency</th>
                <th scope="col">AC</th>
                <th scope="col">AN</th>
                <th scope="col">Hom</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row">
                    {row.label}
                    <small>{row.id}</small>
                  </th>
                  <td>
                    <span
                      className="atlas-gnomad-frequency-bar"
                      style={
                        {
                          '--frequency-share': `${maximum ? (row.af / maximum) * 100 : 0}%`,
                        } as CSSProperties
                      }
                    >
                      {percent(row.af)}
                    </span>
                  </td>
                  <td>{row.ac.toLocaleString()}</td>
                  <td>{row.an.toLocaleString()}</td>
                  <td>{row.homozygote_count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="atlas-gnomad-empty">
          Genetic ancestry group frequencies were not returned for this variant.
        </p>
      )}
      <p className="atlas-gnomad-footnote">
        AC, alternate allele count; AN, total allele number; Hom, homozygous
        alternate individuals.{' '}
        <a
          href="https://gnomad.broadinstitute.org/news/2023-11-genetic-ancestry"
          target="_blank"
          rel="noreferrer"
        >
          How gnomAD defines these groups
        </a>
        .
      </p>
    </DetailHeader>
  );
}

function ConstraintView({ record, toOverview }: DetailProps) {
  const constraint = record.genomic_constraint;
  if (!constraint)
    return (
      <DetailHeader
        title="Genomic constraint of surrounding 1 kb region"
        toOverview={toOverview}
      >
        <p className="atlas-gnomad-empty">
          gnomAD did not return genomic constraint data for this surrounding
          region.
        </p>
      </DetailHeader>
    );
  const position = ((constraint.z + 10) / 20) * 100;
  return (
    <DetailHeader
      title="Genomic constraint of surrounding 1 kb region"
      toOverview={toOverview}
    >
      <p>
        Positive scores indicate fewer rare variants than expected. Negative
        scores indicate more variation than expected.
      </p>
      <figure
        className="atlas-constraint"
        role="img"
        aria-label={`Genomic constraint Z score ${constraint.z.toFixed(2)} on a scale from -10 to 10.`}
      >
        <div className="atlas-constraint__labels" aria-hidden="true">
          <span>More variation</span>
          <span>Expected</span>
          <span>More constrained</span>
        </div>
        <div className="atlas-constraint__thermometer" aria-hidden="true">
          <span className="atlas-constraint__center" />
          <span className="atlas-constraint__threshold atlas-constraint__threshold--ten">
            2.18
          </span>
          <span className="atlas-constraint__threshold atlas-constraint__threshold--one">
            4.0
          </span>
          <span
            className="atlas-constraint__reading"
            style={{ left: `${position}%` }}
          >
            {constraint.z.toFixed(2)}
          </span>
        </div>
        <figcaption aria-hidden="true">
          <span>−10</span>
          <span>0</span>
          <span>+10</span>
        </figcaption>
      </figure>
      <dl className="atlas-external-fields atlas-constraint__fields">
        <Field
          label="Observed variants"
          value={constraint.observed.toLocaleString()}
        />
        <Field label="Expected variants" value={decimal(constraint.expected)} />
        <Field label="Observed / expected" value={decimal(constraint.oe)} />
        <Field
          label="Region"
          value={`${constraint.chrom}:${constraint.start.toLocaleString()}–${constraint.stop.toLocaleString()}`}
        />
        <Field label="Constraint release" value={constraint.dataset_release} />
      </dl>
      <p className="atlas-gnomad-footnote">
        Z ≥ 2.18 marks the top 10% and Z ≥ 4.0 the top 1% of constrained
        non-coding regions.{' '}
        <a
          href="https://gnomad.broadinstitute.org/news/2022-10-the-addition-of-a-genomic-constraint-metric-to-gnomad/"
          target="_blank"
          rel="noreferrer"
        >
          About this metric
        </a>
        .
      </p>
    </DetailHeader>
  );
}

function ClinvarView({ record, toOverview }: DetailProps) {
  const clinvar = record.clinvar;
  if (!clinvar)
    return (
      <DetailHeader title="ClinVar conditions" toOverview={toOverview}>
        <p className="atlas-gnomad-empty">
          No ClinVar record was returned for this variant.
        </p>
      </DetailHeader>
    );
  return (
    <DetailHeader title="ClinVar conditions" toOverview={toOverview}>
      <p>
        ClinVar submissions are clinical assertions about a variant-condition
        relationship, not a diagnosis.
      </p>
      <section className="atlas-clinvar-summary" aria-label="ClinVar summary">
        <div>
          <span>Classification</span>
          <strong>{clinvar.clinical_significance}</strong>
        </div>
        <div>
          <span>Review</span>
          <strong
            className="atlas-clinvar-stars"
            aria-label={`${clinvar.gold_stars} of 4 ClinVar review stars`}
          >
            {'★'.repeat(clinvar.gold_stars)}
            {'☆'.repeat(4 - clinvar.gold_stars)}
          </strong>
        </div>
      </section>
      <dl className="atlas-external-fields atlas-clinvar-fields">
        <Field label="Review status" value={clinvar.review_status} />
        <Field
          label="Last evaluated"
          value={clinvar.last_evaluated ?? 'Not reported'}
        />
        <Field label="ClinVar release" value={clinvar.release_date} />
        <Field
          label="Evidence volume"
          value={`${clinvar.submission_count.toLocaleString()} submissions`}
        />
      </dl>
      <ol className="atlas-clinvar-conditions">
        {clinvar.conditions.map((condition) => (
          <li key={`${condition.medgen_id ?? 'unnamed'}:${condition.name}`}>
            <div>
              {condition.medgen_id ? (
                <a
                  href={`https://www.ncbi.nlm.nih.gov/medgen/${condition.medgen_id}/`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {condition.name}
                </a>
              ) : (
                <strong>{condition.name}</strong>
              )}
              <span>
                {condition.submission_count.toLocaleString()}{' '}
                {condition.submission_count === 1
                  ? 'submission'
                  : 'submissions'}
              </span>
            </div>
            <div className="atlas-clinvar-classifications">
              {condition.classifications.map((classification) => (
                <span key={classification}>{classification}</span>
              ))}
            </div>
          </li>
        ))}
      </ol>
      <a
        className="atlas-clinvar-link"
        href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${clinvar.variation_id}/`}
        target="_blank"
        rel="noreferrer"
      >
        Open ClinVar variation {clinvar.variation_id}
      </a>
    </DetailHeader>
  );
}

interface DetailProps {
  record: GnomadRecord;
  toOverview: () => void;
}

export function GnomadEvidence({ info }: { info: GnomadInfo }) {
  const [view, setView] = useState<GnomadView>('overview');
  const toOverview = () => setView('overview');
  return (
    <>
      {view === 'overview' && (
        <GnomadEvidenceOverview
          info={info}
          navigator={<EvidenceIndex record={info.record} select={setView} />}
        />
      )}
      {view === 'ancestry' && (
        <AncestryView record={info.record} toOverview={toOverview} />
      )}
      {view === 'constraint' && (
        <ConstraintView record={info.record} toOverview={toOverview} />
      )}
      {view === 'clinvar' && (
        <ClinvarView record={info.record} toOverview={toOverview} />
      )}
      <a
        className="atlas-external-source-link"
        href={info.record.source_url}
        target="_blank"
        rel="noreferrer"
      >
        Open this variant in gnomAD <span aria-hidden="true">↗</span>
      </a>
    </>
  );
}
