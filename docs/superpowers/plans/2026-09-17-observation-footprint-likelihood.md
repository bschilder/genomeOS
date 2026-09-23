# Observation-footprint likelihood implementation plan

**Goal:** Add a vectorized, explicit footprint observation operator without treating unqualified
radii or assumed weights as source truth.

**Design:** `docs/superpowers/specs/2026-09-17-observation-footprint-likelihood-design.md`.

## Task 1 — Freeze the support contract and spherical quadrature

- Add failing tests for identifier, coordinate, radius, weight, shape, unit-sphere and version
  refusals.
- Add permutation, antimeridian, polar, spherical-cap moment and deterministic-repeat tests.
- Implement immutable `ObservationSupport`, `uniform_area_disc_support`, and
  `weighted_point_support` in `genomeos/surfaces/footprint.py` using broadcasted arrays.
- Compare the probability mean against the retained frozen nonlinear footprint diagnostic.

## Task 2 — Connect the operator to the fitter

- Add failing tests for exact observation-order alignment and unsupported location semantics.
- Extend `fit_surface` with keyword-only `observation_support` while preserving the existing point
  path byte-for-byte at source level where possible.
- Evaluate the GP at flattened support coordinates; reshape and reduce probabilities with one
  vectorized weighted sum after all observation-level logit terms.
- Record support metadata in `SurfaceFit`; preserve it through save/load and legacy reconstruction.
- Exercise both HSGP and inducing graph construction without running a large scientific fit.

## Task 3 — Verification and review surface

- Run focused footprint and surface-fit tests, then `python scripts/smoke.py`.
- Run Ruff, frozen-contract, module-size, privacy and full Pytest gates.
- Generate no scientific map: this operator-only change has no qualified real input or fitted
  surface to render.
- Commit on the issue branch with `Advances #37 and #189`, push, and open a draft PR describing the
  explicit assumptions and remaining source/benchmark refusals.
