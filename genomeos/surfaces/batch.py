"""Batch orchestration over many variants, with a published exclusion list (design §12, P2).

Fitting one surface is a science problem; fitting a thousand is a bookkeeping problem, and §12
says which way the bookkeeping must fail. **A silently missing variant is indistinguishable from
a variant with no data**, so every variant that goes in must come out either as a fit or as an
exclusion carrying a reason. There is no third outcome and no quiet skip.

That forces an error-handling shape which looks wrong out of context. `run_batch` catches broad
exceptions per variant, because in a batch the alternative to catching is not a clean crash — it
is 999 other variants never being fitted because one had a malformed row. The catch is not a
swallow: every caught failure becomes a row in the exclusion list, with the exception type and
message preserved. `strict=True` re-raises instead, which is what tests and a single-variant
debugging run want.

**The exclusion list is an artifact, not a log.** It is written next to the surfaces, it is meant
to be published with them, and a consumer that reads the surfaces without reading it will
silently mistake "we refused to fit this" for "this variant is absent here". `write_exclusions`
writes it deterministically, sorted, so two runs over the same inputs produce identical bytes and
a diff means something changed.

Exclusion is not failure of the pipeline. §12 refuses to publish a surface that did not converge,
so a long exclusion list is the gate working. It is expected to be long: held-out validation on
HbS excluded 4 of 10 cross-validation folds on convergence grounds alone (#111).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from genomeos.surfaces.fit import ConvergenceError, FitConfig, SurfaceFit, fit_surface

#: Every reason a variant can leave the batch without a surface. Closed on purpose: a new failure
#: mode should be named here and thought about, not folded into `unexpected_error`.
EXCLUSION_REASONS: tuple[str, ...] = (
    "no_observations",
    "too_few_observations",
    "did_not_converge",
    "no_spatial_skill",
    "unexpected_error",
)

#: A *structural* floor, not a quality judgment. The model has at least five free parameters —
#: correlation range, amplitude, intercept, cohort sd and overdispersion — so fewer observations
#: than that cannot identify them under any sampler. Above this the fit is attempted and allowed
#: to fail on convergence, because an exclusion backed by r_hat is evidence whereas an exclusion
#: backed by a round number is a guess. Deliberately low: dropping a variant that might have
#: fitted is worse than spending the compute to find out.
MIN_OBSERVATIONS = 5

#: Relative improvement in held-out MAE over a constant-frequency baseline that a surface must
#: show before it is published (#130).
#:
#: Zero, deliberately. A magnitude threshold here would be the arbitrary constant this gate exists
#: to avoid — the measured spread gives no natural cut point: HbS +2.5%, DRB1*04:04 -0.4%,
#: DRB1*12:01 -4.7%, DRB1*15:01 +24.5%. Any line drawn between 2.5% and 24.5% is a preference.
#:
#: The guard against passing noise is `MIN_SKILL_FOLD_SHARE` instead, which asks for *consistency*
#: rather than magnitude. A variant that beats the baseline on average because one fold went well
#: has not shown spatial skill; one that beats it in most folds has, however small the margin.
MIN_SKILL_MARGIN = 0.0

#: Share of folds in which the surface must beat the baseline. Above one half, so a bare majority
#: is not enough at an even fold count, and a single lucky fold cannot carry a variant.
MIN_SKILL_FOLD_SHARE = 0.6

#: Floor on the inducing-point basis the gate will shrink to. Below a handful of points the
#: sparse approximation cannot represent a field at all, so a variant that would need fewer than
#: this is better refused on observation count than scored on a basis that cannot work.
MIN_INDUCING = 20


@dataclass(frozen=True)
class VariantJob:
    """One variant's inputs. `observations` must already satisfy OBSERVATIONS_SCHEMA."""

    variant_id: str
    observations: pd.DataFrame
    config: FitConfig = field(default_factory=FitConfig)


@dataclass(frozen=True)
class Exclusion:
    """A variant that produced no surface, and why. One row of the published list."""

    variant_id: str
    reason: str
    detail: str
    n_observations: int
    #: Measured held-out skill, where it was measured. Carried on the exclusion so the published
    #: list says *how far* a variant fell short, not only that it did — which is what makes the
    #: threshold recalibratable from the record rather than re-argued (#130).
    skill: float | None = None

    def __post_init__(self) -> None:
        if self.reason not in EXCLUSION_REASONS:
            raise ValueError(
                f"unknown exclusion reason {self.reason!r}; expected one of {EXCLUSION_REASONS}"
            )


@dataclass(frozen=True)
class BatchResult:
    fitted: dict[str, SurfaceFit] = field(repr=False, default_factory=dict)
    exclusions: list[Exclusion] = field(default_factory=list)

    @property
    def n_attempted(self) -> int:
        return len(self.fitted) + len(self.exclusions)

    @property
    def excluded_fraction(self) -> float:
        return len(self.exclusions) / self.n_attempted if self.n_attempted else 0.0

    def exclusion_frame(self) -> pd.DataFrame:
        """The published list, sorted so a diff between runs is meaningful."""
        frame = pd.DataFrame(
            [
                {
                    "variant_id": e.variant_id,
                    "reason": e.reason,
                    "detail": e.detail,
                    "n_observations": e.n_observations,
                }
                for e in self.exclusions
            ],
            columns=["variant_id", "reason", "detail", "n_observations"],
        )
        return frame.sort_values(["reason", "variant_id"]).reset_index(drop=True)

    def __str__(self) -> str:
        lines = [
            f"{len(self.fitted)}/{self.n_attempted} variants fitted "
            f"({self.excluded_fraction:.0%} excluded)"
        ]
        counts: dict[str, int] = {}
        for exclusion in self.exclusions:
            counts[exclusion.reason] = counts.get(exclusion.reason, 0) + 1
        for reason, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  excluded {count:>5}  {reason}")
        return "\n".join(lines)


def measure_spatial_skill(
    observations: pd.DataFrame, config: FitConfig, *, n_folds: int
) -> tuple[float, float, int]:
    """`(mean relative MAE improvement, share of folds improved, folds scored)`.

    Spatially blocked folds, because that is the question: does the surface predict where there
    is no nearby survey? Random or grouped folds leave a neighbour in training and measure
    interpolation, which every surface passes and which #109 measured at four times the apparent
    skill of the honest test.

    Folds that fail to converge are dropped rather than scored, and the count is returned so a
    variant judged on one surviving fold is visible as such.
    """
    from dataclasses import replace

    from genomeos.validation.crossval import cross_validate

    # A fold trains on (k-1)/k of the data, so an `n_inducing` sized against the full set can
    # breach `fit_surface`'s M<<N guard once the fold is taken and the whole gate raises. The
    # caller supplies one config for the variant; shrinking it here is the only place that knows
    # the fold size, and silently failing the gate would be worse than a smaller basis.
    n_train = len(observations) * (n_folds - 1) // n_folds
    config = replace(config, n_inducing=max(MIN_INDUCING, min(config.n_inducing, n_train // 2)))

    result = cross_validate(observations, config, n_folds, "spatial")
    if not result.folds:
        return float("nan"), 0.0, 0
    gains = [
        (fold.baseline_mae - fold.mae) / fold.baseline_mae
        for fold in result.folds
        if fold.baseline_mae > 0
    ]
    if not gains:
        return float("nan"), 0.0, 0
    improved = sum(1 for g in gains if g > 0) / len(gains)
    return float(sum(gains) / len(gains)), float(improved), len(gains)


def run_batch(
    jobs: Iterable[VariantJob],
    *,
    strict: bool = False,
    on_progress: Any = None,
    skill_folds: int = 0,
    min_skill_margin: float = MIN_SKILL_MARGIN,
    min_skill_fold_share: float = MIN_SKILL_FOLD_SHARE,
) -> BatchResult:
    """Fit every job, recording rather than raising on the ones that fail.

    `strict=True` re-raises instead of excluding, which is what a single-variant debugging run
    wants; the batch path must not use it, or one bad variant ends the run.

    `skill_folds > 0` turns on the **skill gate** (#130): each fitted variant is cross-validated
    against a constant-frequency baseline and excluded unless it beats it. Off by default because
    it costs a full k-fold refit per variant — five folds across 767 alleles is five times the
    batch — so switching it on is a decision the caller makes with the compute in front of them.

    A surface that cannot beat one global number is not a finding, and emitting no surface is a
    valid output (§9). Without the gate the pipeline publishes those surfaces indistinguishably
    from the ones that work.
    """
    fitted: dict[str, SurfaceFit] = {}
    exclusions: list[Exclusion] = []

    for job in jobs:
        n = len(job.observations)
        if on_progress is not None:
            on_progress(job.variant_id, n)

        if n == 0:
            exclusions.append(
                Exclusion(job.variant_id, "no_observations", "no rows supplied", 0)
            )
            continue
        if n < MIN_OBSERVATIONS:
            exclusions.append(
                Exclusion(
                    job.variant_id,
                    "too_few_observations",
                    f"{n} observations, minimum {MIN_OBSERVATIONS}",
                    n,
                )
            )
            continue

        try:
            fit = fit_surface(job.observations, job.config)
            if skill_folds > 0:
                skill, share, scored = measure_spatial_skill(
                    job.observations, job.config, n_folds=skill_folds
                )
                if scored == 0:
                    exclusions.append(
                        Exclusion(
                            job.variant_id, "no_spatial_skill",
                            "no cross-validation fold converged, so skill is unmeasured",
                            n, None,
                        )
                    )
                    continue
                if not (skill > min_skill_margin and share >= min_skill_fold_share):
                    exclusions.append(
                        Exclusion(
                            job.variant_id, "no_spatial_skill",
                            f"held-out MAE improves on a constant baseline by {skill:+.1%} "
                            f"in {share:.0%} of {scored} folds; needs >{min_skill_margin:+.1%} "
                            f"in >={min_skill_fold_share:.0%}",
                            n, round(skill, 4),
                        )
                    )
                    continue
            fitted[job.variant_id] = fit
        except ConvergenceError as error:
            # §12: a fit that has not mixed is excluded rather than published. Named separately
            # from `unexpected_error` because it is the expected failure, not a defect.
            if strict:
                raise
            exclusions.append(Exclusion(job.variant_id, "did_not_converge", str(error), n))
        except Exception as error:  # noqa: BLE001 - see the module docstring
            if strict:
                raise
            exclusions.append(
                Exclusion(
                    job.variant_id,
                    "unexpected_error",
                    f"{type(error).__name__}: {error}",
                    n,
                )
            )

    return BatchResult(fitted=fitted, exclusions=exclusions)


def write_exclusions(result: BatchResult, path: Path, *, data_version: str) -> Path:
    """Write the published exclusion list.

    Written even when empty. An absent file is ambiguous — it could mean nothing was excluded or
    that the list was never produced — and this file exists precisely to remove that ambiguity.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = result.exclusion_frame()
    payload = {
        "data_version": data_version,
        "n_attempted": result.n_attempted,
        "n_fitted": len(result.fitted),
        "n_excluded": len(result.exclusions),
        "exclusions": frame.to_dict(orient="records"),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def jobs_from_sources(
    sources: dict[str, pd.DataFrame], config: FitConfig | None = None
) -> Iterator[VariantJob]:
    """Split loaded observations into one job per `variant_id`.

    `fit_surface` refuses a frame containing more than one variant, so this is the only supported
    way to go from a mixed observations store to a batch.
    """
    config = config or FitConfig()
    for source_name in sorted(sources):
        frame = sources[source_name]
        for variant_id in sorted(frame["variant_id"].unique()):
            subset = frame[frame["variant_id"] == variant_id].reset_index(drop=True)
            yield VariantJob(variant_id=str(variant_id), observations=subset, config=config)
