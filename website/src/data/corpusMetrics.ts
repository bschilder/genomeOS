export interface CountMetric {
  components: Record<string, number>;
  isDeduplicated: boolean;
}

export const corpusMetrics = {
  sourceDataset: 'bschilder/genomeos-data',
  sourceRevision: 'fc17bc1c1d96a0d0766746dcf26277ccdc669717',
  sourceUpdatedAt: '2026-08-27',
  countedAt: '2026-09-06',
  variants: {
    components: {
      afndAlleleIdentifiersAfterCurrentFilters: 4_391,
      hbsVariant: 1,
    },
    isDeduplicated: true,
  },
  people: {
    components: {
      afndPopulationRecords: 657_287,
      hbsTypedParticipants: 5_717_140,
      g6pdHemizygousMaleParticipants: 316_448,
    },
    isDeduplicated: false,
  },
  diseases: {
    components: {
      sickleCellDisease: 1,
      g6pdDeficiency: 1,
    },
    isDeduplicated: true,
  },
} as const satisfies Record<string, string | CountMetric>;

export function metricTotal(metric: CountMetric): number {
  const counts = Object.values(metric.components);
  if (
    !counts.length ||
    counts.some((count) => !Number.isSafeInteger(count) || count < 0)
  ) {
    throw new Error(
      'Corpus metric components must be non-negative safe integers.',
    );
  }
  return counts.reduce((total, count) => total + count, 0);
}

if (!/^[0-9a-f]{40}$/.test(corpusMetrics.sourceRevision)) {
  throw new Error(
    'Corpus metrics must pin a full immutable Hugging Face revision.',
  );
}
