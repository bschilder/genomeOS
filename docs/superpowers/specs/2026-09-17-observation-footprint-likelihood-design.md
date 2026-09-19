# Observation-footprint likelihood design

**Issue:** #37. **Atlas:** design §7 and §7.1. **Program:** #189 WP2.

## 1. Scientific objective and claim

When a reviewed observation describes spatial recruitment support, evaluate the latent field over
that support instead of treating its display coordinate as a pinpoint measurement. The bounded
claim is that GenomeOS can average frequency-scale probabilities over an explicitly supplied,
normalized spatial support and use that mean in the existing count likelihood.

This does not claim that every `radius_km` is a recruitment footprint. It does not choose a
recruitment distribution from a radius, certify the MAP area classes in #190, infer present-day
residence for HGDP, cap effective sample sizes in #123, or establish predictive improvement.

## 2. Measurable output and acceptance evidence

The implementation must provide:

1. a deterministic vectorized uniform-spherical-area disc quadrature whose points lie on the unit
   sphere and whose weights are finite, nonnegative, normalized per observation, and invariant to
   input permutation;
2. an explicit weighted-point constructor for externally computed population weights, without any
   raster, filesystem, network, or fallback inside the science module;
3. exact source-record alignment between observations and support;
4. probability-scale averaging after spatial, design, cohort and nugget logit terms are composed;
5. unchanged point-fit behavior when no support object is supplied;
6. hard refusal for malformed coordinates, radii, weights, identifiers, support versions,
   unsupported count-location semantics, or mismatched observation order;
7. focused numerical tests against independent spherical-cap identities and the frozen nonlinear
   footprint diagnostic, followed by smoke, full CI, contract, module-size and privacy gates.

The implementation is accepted as engineering and observation-operator correctness evidence. A
paired benchmark improvement and source qualification remain separate WP2/WP0 gates.

## 3. Interface and data flow

Create `genomeos.surfaces.footprint` with the immutable public contract:

```python
ObservationSupport(
    observation_ids: tuple[str, ...],
    unit_sphere: np.ndarray,       # (observations, support_points, 3)
    weights: np.ndarray,           # (observations, support_points)
    weighting: Literal["uniform_area", "population_weighted"],
    location_model: Literal["independent_location_per_trial"],
    support_version: str,
)

uniform_area_disc_support(
    observation_ids, lat, lon, radius_km,
    *, radial_order, angular_order, support_version,
) -> ObservationSupport

weighted_point_support(
    observation_ids, lat, lon, weights,
    *, weighting, location_model, support_version,
) -> ObservationSupport
```

`fit_surface(observations, config, *, observation_support=None)` keeps the current point model when
the keyword is absent. When support is supplied, its identifiers must exactly match the validated
P1 row order. The GP evaluates all support points in one flattened matrix. The model reshapes the
latent logit to `(observations, support_points)`, broadcasts observation-level design/cohort/nugget
terms, applies inverse-logit pointwise, and takes one vectorized weighted sum per observation.
The resulting vector remains the existing `p` consumed by `Binomial` or `BetaBinomial`.

`SurfaceFit` records immutable support metadata: operator convention, weighting, declared
count-location model, support version and points per observation. This metadata survives save/load.

## 4. Geometry and vectorization

For Earth radius `R`, disc radius `r`, uniform `u` in `[0,1]`, and uniform azimuth `theta`, spherical
surface-area sampling uses

```text
d = 2 R asin(sqrt(u) sin(r / (2 R))).
```

Gauss-Legendre nodes integrate `u`; an equally spaced periodic rule integrates azimuth. A single
broadcasted geodesic-forward calculation produces every `(observation, radial, azimuth)` point.
There is no observation-by-point Python loop. The fitter likewise flattens once, evaluates the GP
once, reshapes once and reduces the support axis once.

## 5. Assumptions and refusal conditions

- `uniform_area` means a declared uniform spherical-area recruitment assumption. It is never
  reported as observed recruitment truth.
- `population_weighted` means the caller supplied reviewed point weights. This module does not
  derive population weights or select a population raster.
- The first supported count-location model is `independent_location_per_trial`. Under this model,
  count trials independently draw locations from the supplied support, so the count probability is
  governed by the support-mean frequency. The name is retained in the artifact because it is a
  scientific assumption, not an implementation detail.
- A common uncertain location, per-person shared locations, or other clustered location model has a
  different count law even at the same mean. Those cases are refused rather than approximated. The
  retained count-dependence diagnostic demonstrates why.
- Radius must be finite, strictly positive, and smaller than a hemisphere. No default, area-class
  conversion, coordinate-precision inference or clipping is permitted.
- Point observations continue through the existing path. Passing no support is an explicit call to
  the legacy point interface; it does not convert a nonzero radius into a disc.

## 6. Downstream consumers and limits

The immediate consumer is a controlled B2 observation-operator comparison under #189. A real-data
comparison may begin only after contributing rows have reviewed support semantics. Uniform-area
versus population-weighted sensitivity uses two separately versioned `ObservationSupport` objects
with otherwise identical folds and configuration.

This change does not resolve #190, #123, the location-sharing question for aggregated studies,
external validation, convergence acceptance, or the Atlas golden tests. It produces no surface,
burden layer, or publication-eligible result by itself.
