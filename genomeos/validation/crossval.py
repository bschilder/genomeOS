"""Held-out predictive validation of the surface fit (design §7, §8).

§8's golden tests compare *aggregate* national estimates against published ones. That is a
necessary test and not a sufficient one: a model can reproduce national totals while predicting
individual localities badly, because aggregation hides error. This module asks the question the
map itself makes — **what is the allele frequency somewhere we did not measure?**

**Folds are spatial blocks, not random rows.** Allele frequency is spatially autocorrelated, so
a randomly held-out survey usually has a training survey a few kilometres away and can be
"predicted" by near-interpolation. That measures smoothing, not skill. Holding out contiguous
regions asks the real question. Both are computed, because the *gap* between them quantifies how
much apparent skill is autocorrelation rather than signal.

**Calibration is the headline, not error.** §4's defence against manufactured clines rests on the
uncertainty being real. A model with small error and 60% coverage of its own 95% intervals is
worse than useless here: every credible interval on the published map would be a false claim.

Reported per fold and pooled:

- ``coverage_*_predictive`` — share of held-out observations inside the posterior predictive
  interval for a survey of that size. This is the calibration statistic (#110).
- ``coverage_*_latent`` — the same against the latent-frequency interval. Reported for
  contrast only: it omits sampling noise and the cohort offset, so it under-covers whatever
  the model does. Kept because the gap between the two is informative.
- (superseded) share of held-out observations inside the predicted
  interval. Should approach 0.95 and 0.50; **below is overconfidence, above is uselessly wide**.
- ``mae`` / ``rmse`` on the allele-frequency scale.
- ``log_score`` — mean predictive log-likelihood of the held-out counts under the fitted
  likelihood. A proper scoring rule, so it cannot be gamed by widening intervals.
- The same metrics for a **constant baseline** (the training-set pooled frequency). A spatial
  model that cannot beat "assume the global average everywhere" has no spatial skill at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from genomeos.surfaces.fit import ConvergenceError, FitConfig, fit_surface, to_unit_sphere

SEED = 42
FOLD_STRATEGIES: tuple[str, ...] = ("spatial", "random")


@dataclass(frozen=True)
class FoldResult:
    fold: int
    n_train: int
    n_test: int
    #: Coverage of the *posterior predictive for a new survey* — the calibration claim, and the
    #: headline number. See `SurfaceFit.predict_observation` and #110.
    coverage_95_predictive: float
    coverage_50_predictive: float
    #: Coverage of the *latent frequency* interval. Reported because it is what the map claims,
    #: but it is not a calibration statistic: it omits sampling noise and the cohort offset that
    #: are present in any real survey, so it under-covers by construction (#110).
    coverage_95_latent: float
    coverage_50_latent: float
    mae: float
    rmse: float
    log_score: float
    baseline_mae: float
    baseline_log_score: float


@dataclass(frozen=True)
class FoldFailure:
    """A fold whose fit did not converge. Recorded, not fatal.

    A single unconverged fold must not destroy the whole run: folds train on a fraction of the
    data, so some will mix worse than the full fit, and eight hours of work was once lost to one
    of them raising. The failure is reported and excluded from the means — never silently
    averaged away as if it had succeeded.
    """

    fold: int
    n_train: int
    n_test: int
    error: str


@dataclass(frozen=True)
class CrossValidation:
    strategy: str
    folds: list[FoldResult] = field(repr=False)
    failures: list[FoldFailure] = field(default_factory=list, repr=False)

    @property
    def n_attempted(self) -> int:
        return len(self.folds) + len(self.failures)

    def _mean(self, attribute: str) -> float:
        if not self.folds:
            return float("nan")
        return float(np.mean([getattr(f, attribute) for f in self.folds]))

    @property
    def skill(self) -> float:
        """Improvement in mean log score over the constant baseline. Positive means the spatial
        model earns its complexity; <= 0 means it does not."""
        return self._mean("log_score") - self._mean("baseline_log_score")

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame([f.__dict__ for f in self.folds])

    def __str__(self) -> str:
        header = f"{self.strategy} cross-validation — {len(self.folds)}/{self.n_attempted} folds scored"
        if self.failures:
            header += f"  ({len(self.failures)} did not converge)"
        if not self.folds:
            return header + "\n  no fold converged; nothing to report"
        return "\n".join(
            [
                header,
                f"  predictive coverage  95% : {self._mean('coverage_95_predictive'):.2f}"
                f"  (target 0.95)  <- calibration",
                f"  predictive coverage  50% : {self._mean('coverage_50_predictive'):.2f}"
                f"  (target 0.50)",
                f"  latent-frequency cov 95% : {self._mean('coverage_95_latent'):.2f}"
                f"  (not a calibration statistic; see #110)",
                f"  MAE (allele frequency)   : {self._mean('mae'):.4f}"
                f"   baseline {self._mean('baseline_mae'):.4f}",
                f"  RMSE                     : {self._mean('rmse'):.4f}",
                f"  log score                : {self._mean('log_score'):.3f}"
                f"   baseline {self._mean('baseline_log_score'):.3f}",
                f"  skill over baseline      : {self.skill:+.3f}",
            ]
        )


def make_folds(
    observations: pd.DataFrame,
    n_folds: int = 5,
    strategy: str = "spatial",
    seed: int = SEED,
) -> np.ndarray:
    """Fold index per observation.

    ``spatial`` clusters locations so each fold is a contiguous region — the honest test.
    ``random`` shuffles rows, which leaks neighbours between train and test.
    """
    if strategy not in FOLD_STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; expected one of {FOLD_STRATEGIES}")
    if not 2 <= n_folds <= len(observations):
        raise ValueError("n_folds must be between 2 and the number of observations")

    rng = np.random.default_rng(seed)
    if strategy == "random":
        return rng.permutation(len(observations)) % n_folds

    from scipy.cluster.vq import kmeans2

    x = to_unit_sphere(observations["lat"], observations["lon"])
    _, labels = kmeans2(x, n_folds, minit="++", seed=seed, iter=40)
    return labels


def _log_score(ac: np.ndarray, an: np.ndarray, p: np.ndarray) -> float:
    """Mean binomial log-likelihood per held-out observation, ignoring the constant term.

    A proper scoring rule: unlike coverage it cannot be improved by simply widening intervals.
    """
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(np.mean(ac * np.log(p) + (an - ac) * np.log1p(-p)))


def cross_validate(
    observations: pd.DataFrame,
    config: FitConfig | None = None,
    n_folds: int = 5,
    strategy: str = "spatial",
    seed: int = SEED,
) -> CrossValidation:
    """Fit on each fold's complement and score the held-out surveys."""
    config = config or FitConfig()
    # Each fold trains on (k-1)/k of the data, so `n_inducing` has to satisfy fit_surface's
    # M<<N guard against the *fold* size rather than the full dataset.
    folds = make_folds(observations, n_folds, strategy, seed)
    observations = observations.reset_index(drop=True)

    results: list[FoldResult] = []
    failures: list[FoldFailure] = []
    for fold in sorted(set(folds)):
        test_mask = folds == fold
        train, test = observations[~test_mask], observations[test_mask]
        if train.empty or test.empty:
            continue

        try:
            fit = fit_surface(train, config)
        except ConvergenceError as error:
            # Record and continue. See FoldFailure.
            failures.append(
                FoldFailure(int(fold), len(train), len(test), str(error))
            )
            continue
        lat, lon = test["lat"].to_numpy(), test["lon"].to_numpy()
        ac = test["ac"].to_numpy(dtype=float)
        an = test["an"].to_numpy(dtype=float)
        observed = ac / an

        predicted = fit.predict(lat=lat, lon=lon)
        median = predicted["post_median"].to_numpy()

        # Calibration is scored against the posterior predictive for a survey of this size, not
        # against the latent-frequency interval. The latent interval describes the underlying
        # frequency; `observed` is a noisy realisation of it, carrying binomial sampling noise
        # and its own cohort offset. Comparing the two under-covers however good the model is,
        # which is what produced a 0.10 coverage on the first run (#110).
        replicated = fit.predict_observation(lat=lat, lon=lon, an=an)
        inside_95 = (observed >= replicated["pred_q025"]) & (observed <= replicated["pred_q975"])
        inside_50 = (observed >= replicated["pred_q25"]) & (observed <= replicated["pred_q75"])
        # Kept for contrast: the gap between the two is the size of the components the map's
        # interval leaves out.
        latent_95 = (observed >= predicted["q025"]) & (observed <= predicted["q975"])
        latent_50 = (observed >= predicted["q25"]) & (observed <= predicted["q75"])

        baseline_p = float(train["ac"].sum() / train["an"].sum())
        results.append(
            FoldResult(
                fold=int(fold),
                n_train=len(train),
                n_test=len(test),
                coverage_95_predictive=float(inside_95.mean()),
                coverage_50_predictive=float(inside_50.mean()),
                coverage_95_latent=float(latent_95.mean()),
                coverage_50_latent=float(latent_50.mean()),
                mae=float(np.mean(np.abs(median - observed))),
                rmse=float(np.sqrt(np.mean((median - observed) ** 2))),
                log_score=_log_score(ac, an, median),
                baseline_mae=float(np.mean(np.abs(baseline_p - observed))),
                baseline_log_score=_log_score(ac, an, np.full_like(observed, baseline_p)),
            )
        )
    return CrossValidation(strategy=strategy, folds=results, failures=failures)
