/**
 * Cold-load profiles, network presets and budgets (fast-load design §B.1).
 *
 * Network presets are the Chrome DevTools "Fast 4G" / "Slow 4G" values, not
 * Lighthouse's.
 */
export interface NetworkConditions {
  latency: number;
  downloadThroughput: number;
  uploadThroughput: number;
}

export interface ColdLoadBudgets {
  observationsVisibleMs: number;
  surfaceVisibleMs: number;
  atlasLongFrameMs: number;
  revealMs: number | null;
}

export type ColdLoadProfileName =
  'desktop' | 'mobile-fast-4g' | 'mobile-slow-4g';

export interface ColdLoadProfile {
  name: ColdLoadProfileName;
  viewport: { width: number; height: number };
  deviceScaleFactor: number;
  isMobile: boolean;
  hasTouch: boolean;
  cpuThrottlingRate: number;
  network: NetworkConditions | null;
  budgets: ColdLoadBudgets;
  /** Per-run ceiling for reaching the settled state (not a budget). */
  timeoutMs: number;
}

export const FAST_4G: NetworkConditions = {
  latency: 165,
  downloadThroughput: 1_012_500,
  uploadThroughput: 168_750,
};

export const SLOW_4G: NetworkConditions = {
  latency: 562.5,
  downloadThroughput: 180_000,
  uploadThroughput: 84_375,
};

export const COLD_LOAD_RUNS = 3;
export const QUIET_PERIOD_MS = 1_000;

const MOBILE: Pick<
  ColdLoadProfile,
  | 'viewport'
  | 'deviceScaleFactor'
  | 'isMobile'
  | 'hasTouch'
  | 'cpuThrottlingRate'
> = {
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  cpuThrottlingRate: 4,
};

export const COLD_LOAD_PROFILES: readonly ColdLoadProfile[] = [
  {
    name: 'desktop',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    isMobile: false,
    hasTouch: false,
    cpuThrottlingRate: 1,
    network: null,
    budgets: {
      observationsVisibleMs: 1_500,
      surfaceVisibleMs: 2_500,
      atlasLongFrameMs: 200,
      revealMs: null,
    },
    timeoutMs: 60_000,
  },
  {
    name: 'mobile-fast-4g',
    ...MOBILE,
    network: FAST_4G,
    budgets: {
      observationsVisibleMs: 4_000,
      surfaceVisibleMs: 6_000,
      atlasLongFrameMs: 800,
      revealMs: 1_000,
    },
    timeoutMs: 120_000,
  },
  {
    name: 'mobile-slow-4g',
    ...MOBILE,
    network: SLOW_4G,
    budgets: {
      observationsVisibleMs: 13_000,
      surfaceVisibleMs: 18_000,
      atlasLongFrameMs: 800,
      revealMs: null,
    },
    timeoutMs: 180_000,
  },
];
