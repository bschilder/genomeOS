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

- ``coverage_95`` / ``coverage_50`` — share of held-out observations inside the predicted
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

from genomeos.surfaces.fit import FitConfig, fit_surface, to_unit_sphere

SEED = 42
FOLD_STRATEGIES: tuple[str, ...] = ("spatial", "random")


@dataclass(frozen=True)
class FoldResult:
    fold: int
    n_train: int
    n_test: int
    coverage_95: float
    coverage_50: float
    mae: float
    rmse: float
    log_score: float
    baseline_mae: float
    baseline_log_score: float


@dataclass(frozen=True)
class CrossValidation:
    strategy: str
    folds: list[FoldResult] = field(repr=False)

    def _mean(self, attribute: str) -> float:
        return float(np.mean([getattr(f, attribute) for f in self.folds]))

    @property
    def skill(self) -> float:
        """Improvement in mean log score over the constant baseline. Positive means the spatial
        model earns its complexity; <= 0 means it does not."""
        return self._mean("log_score") - self._mean("baseline_log_score")

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame([f.__dict__ for f in self.folds])

    def __str__(self) -> str:
        return "\n".join(
            [
                f"{self.strategy} {len(self.folds)}-fold cross-validation",
                f"  coverage of 95% interval : {self._mean('coverage_95'):.2f}  (target 0.95)",
                f"  coverage of 50% interval : {self._mean('coverage_50'):.2f}  (target 0.50)",
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
    folds = make_folds(observations, n_folds, strategy, seed)
    observations = observations.reset_index(drop=True)

    results: list[FoldResult] = []
    for fold in sorted(set(folds)):
        test_mask = folds == fold
        train, test = observations[~test_mask], observations[test_mask]
        if train.empty or test.empty:
            continue

        fit = fit_surface(train, config)
        predicted = fit.predict(lat=test["lat"].to_numpy(), lon=test["lon"].to_numpy())

        ac = test["ac"].to_numpy(dtype=float)
        an = test["an"].to_numpy(dtype=float)
        observed = ac / an
        median = predicted["post_median"].to_numpy()

        # Coverage is on the observed *frequency*, which is what the map claims about.
        inside_95 = (observed >= predicted["q025"]) & (observed <= predicted["q975"])
        inside_50 = (observed >= predicted["q25"]) & (observed <= predicted["q75"])

        baseline_p = float(train["ac"].sum() / train["an"].sum())
        results.append(
            FoldResult(
                fold=int(fold),
                n_train=len(train),
                n_test=len(test),
                coverage_95=float(inside_95.mean()),
                coverage_50=float(inside_50.mean()),
                mae=float(np.mean(np.abs(median - observed))),
                rmse=float(np.sqrt(np.mean((median - observed) ** 2))),
                log_score=_log_score(ac, an, median),
                baseline_mae=float(np.mean(np.abs(baseline_p - observed))),
                baseline_log_score=_log_score(ac, an, np.full_like(observed, baseline_p)),
            )
        )
    return CrossValidation(strategy=strategy, folds=results)
