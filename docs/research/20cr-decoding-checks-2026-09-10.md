# 20CRv3: bounded calendar and precipitation decoding checks

Status: `automated_proposal` / `pending`, 2026-09-10. Advances #189, WP3/WP7,
Atlas design §§4–9,12. Companion to the
[temporal-source qualification](temporal-climate-source-qualification-2026-09-10.md).
These are source-format diagnostics, not climate-feature admission or an
allele-frequency improvement claim.

## Scientific contract

Objective: establish what a historical precipitation value actually measures
before using it to predict withheld allele counts. Output: reproducible primary
source identities, explicit transformations and a retained inconsistency.
The future interface is an immutable offline feature artifact with native
space/time support, source/derivation provenance and missingness. Its consumers
are matched climate-family benchmarks, not the serving path.

Acceptance requires correct units/calendar, complete temporal support and
internally consistent aggregation before a derived value is usable. Missing or
conflicting evidence cannot be silently repaired. This check uses nominal grid
points, not genetic sampling sites, ancestral paths or verified resident support.

## Resolved interpretation

The [NOAA catalogue](https://psl.noaa.gov/data/gridded/data.20thC_ReanV3.html)
links the monthly `Monthlies/accumsSI-MO/apcp.mon.mean.nc` and yearly
`accumsSI/apcp.1806.nc`, `accumsSI/apcp.1980.nc`, and
`accumsMO/apcp.1981.nc` products under `Datasets/20thC_ReanV3`.
The exact January 1806 parent [metadata](https://psl.noaa.gov/thredds/dodsC/Datasets/20thC_ReanV3/accumsSI/apcp.1806.nc.das)
identifies three-hour precipitation amounts in `kg/m^2`, ensemble means over
80 members, and interval-start time coordinates. It does not provide explicit
parent time bounds.

The [author's archive documentation](https://reanalyses.org/task-forces/20crv3-early-access-details)
describes adjacent three-hour accumulation buckets assembled across forecast
cycles. Together with the parent metadata, this supports summing delivered
buckets, not differencing them as if each were cumulative since a forecast reset.
No instantaneous-rate or seconds conversion is justified for this amount field.

These files declare CF-1.2 and omit `calendar`. The
[CF-1.2 time-coordinate convention](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.2/build/cf-conventions.html)
defines the default mixed Gregorian/Julian calendar. All inspected dates are
after 1800, on its Gregorian side. Applying that declared standard is an explicit
derivation, not a claim that NOAA printed a calendar attribute.

The monthly product supplies hour bounds but stores a mean of three-hour
amounts, not a monthly accumulation. For complete, internally consistent months:

```text
interval_count = (end_bound_hours - start_bound_hours) / 3
monthly_total_kg_m2 = monthly_mean_kg_m2 * interval_count
annual_total_kg_m2 = sum(complete monthly totals)
```

Bounds must establish exact interval coverage; a plausible calendar label alone
does not establish the denominator used to produce a mean. Ensemble means also
do not qualify nonlinear exposure/extreme summaries or uncertainty propagation
that requires coherent ensemble members.

## Actual small checks and retained discrepancy

At latitude 0°, longitude 0°, January 1980 (SI) and January 1981 (MO) monthly
values approximately agree with the means of all 248 corresponding three-hour
parent amounts. The observed parent sums are 48.9 and 112.7
`kg/m^2`, respectively. This verifies these specific queried values only, not
the full grid, all months, global coverage or the complete SI/MO transition.

Experimental January 1806 behaves differently at three neighboring grid points:

| Longitude at latitude 0° | Mean of all 248 parent values | Mean of parent indices 8–247 | Published monthly mean |
| --- | ---: | ---: | ---: |
| 0° | 0.240725806 | 0.236666667 | 0.23666663 |
| 1° | 0.241935484 | 0.240416667 | 0.24041669 |
| 2° | 0.270161290 | 0.268750000 | 0.26875004 |

Values are `kg/m^2` per three-hour bucket before averaging. The parent time
coordinates run from 52584 to 53325 hours since 1800-01-01, in three-hour steps;
the monthly bounds are 52584–53328, corresponding to January 1–February 1, 1806.
Thus the first eight parent values are inside the stated month. Independent
arithmetic reproduced the three means and nonzero first-day sums.

The monthly values approximately match a 240-value/30-day slice, rather than all
248 intervals within the published 31-day bound. This is an observed discrepancy, not an
established explanation of NOAA's processing or a provider-confirmed bug.
Multiplying those monthly means by 248 is therefore not admitted as a January 1806
total. Untested early months are not presumed clean.

This need not discard the higher-frequency source: a separate product derived
by summing every independently verified parent interval may be testable. It must
carry its own provenance and complete-support checks, not overwrite or silently
repair the monthly product. Temperature and other months require their own checks.

## Complete-year and temperature follow-up

A subsequent bounded check compared all three-hour values with all twelve
monthly means at the returned grid coordinate 30° N, 31° E for 1980 (SI) and
1981 (MO). Both temperature and precipitation had complete, finite half-open
year windows: 2,928 intervals in the leap year and 2,920 in the common year.
The temperature parents were the catalogue-linked `2mSI/air.2m.1980.nc` and
`2mMO/air.2m.1981.nc`; monthly temperature was
`Monthlies/2mSI-MO/air.2m.mon.mean.nc`. No genetic site or land-support identity
is assigned to this nominal grid coordinate.

Duration-weighted annual temperature and summed annual precipitation differed
from the corresponding monthly-derived diagnostics by amounts small when
expressed in stored-value Float32 ULPs. However, some monthly differences exceeded one stored-value ULP, reaching
about 1.83 ULP. Opposite-signed monthly residuals partly cancel annually: annual
agreement does not establish that each month agrees. The one-ULP and accumulated
annual thresholds are **report-declared diagnostic scales**; retained evidence
does not establish prospective declaration. They are not environmental-error
models or acceptance thresholds for predictive performance.

For January 1806 temperature at the three original cells, the all-248 means
differed from the monthly values by approximately -1.61, -0.83 and +10.28 ULP.
Removing the first eight intervals worsened every comparison. Temperature thus
does not support the closer 240-interval pattern seen in precipitation. Even
the latter pattern is approximate: after explicit Float32 decoding, its residuals
were about 1.23–2.49 ULP, not exact equality or a confirmed omission mechanism.

An independent retained-data check reproduced the annual arithmetic and matched
all 12,491 field values bitwise between eight ASCII/DODS subset pairs after
decoding the declared Float32 representation. This excludes decimal-printing
differences for those pairs, not unknown upstream aggregation/rounding effects.
There is no new claim about global coverage, actual environmental accuracy,
uncertainty calibration, or usefulness for predicting allele frequency.

## Reproduction and boundaries

The parent check used the provider's OPeNDAP ASCII response with the literal
constraint `apcp[0:1:247][90:1:90][0:1:2]`, together with corresponding `time`,
`lat` and `lon` coordinates. Its retained 10809-byte response SHA-256 is
`c38ded88bd5289c60f041a9b6e7a96dab2094f1d8317849a842923502ac5efa7`.
The January 1806 monthly comparison used time index 0 and the same coordinate
values; January 1980 and January 1981 used indices 2088 and 2100, respectively.
These are response hashes, not whole-NetCDF checksums. Raw responses, exact
retrievals and arithmetic transcripts remain local source-inspection evidence;
no climate arrays or genetic records are committed by this note.

The leap/common-year and temperature follow-up above is complete at its stated
small scope; it does not admit an extractor or climate feature. Its additional
retained captures total 968,446 bytes, not complete NetCDF assets. Provider CC0
terms were inspected in the preceding qualification;
asset identity, decoding and genetic utility remain distinct gates. Later model
experiments must use unchanged outcome rows, dependency-aware held-out partitions
and source-family controls, with failed coverage and folds retained explicitly.
