# Variant Normalization Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reviewed lookup from an internal `variant_id` to a normalized GRCh38 identity, so legacy-named variants can carry coordinate-keyed external annotations, without changing any published identity.

**Architecture:** A new registry module mirroring P0 (`genomeos/registry/schema.py` + `build.py`): a pandera schema, a loader that enforces cross-field invariants pandera cannot express, and one resolution function returning `None` for "no reviewed entry". The web exporter becomes its first consumer, replacing an identifier-shape regex with a registry lookup. Rows are hand-authored and reviewed; no code resolves a variant automatically.

**Tech Stack:** Python 3.12, pandera (`pandera.pandas`), pandas, pytest. No new dependencies.

**Spec:** [`../specs/2026-09-10-variant-normalization-registry-design.md`](../specs/2026-09-10-variant-normalization-registry-design.md)

## Known gap in the spec, to raise before Task 5

Spec §5 states as an invariant that "a row may only be `resolved` if two **independent** resources
returned the same placement", but the schema table only requires `reference_resource` to be present
and versioned — it does not require it to name *two*. This plan follows the schema table and
enforces presence, leaving "two resources" as a process rule in the Task 5 runbook rather than a
machine check.

That is a deliberate, reviewable choice, not an oversight: the field is free text, so a check could
only assert that it names two things, not that they are genuinely independent. **Raise it with the
maintainer before Task 5** — if a machine check is wanted, the field needs splitting into two
columns first, which changes the frozen contract and therefore belongs in Task 1, not later.

## Global Constraints

- `from __future__ import annotations` at the top of every new module.
- Module docstrings cite the design section they implement.
- Line length 110 (`ruff check .` must pass; `ruff format` is **not** a project gate).
- No column has a default. A missing required field is a hard error, never a blank or a fallback.
- **No published `variant_id`, `source_record_id`, or artifact identity may change.** This is the acceptance evidence for the whole plan (spec §1). Any diff to `website/public/data/atlas/catalog.json` other than a deliberately added external resource means the work is wrong.
- **Correction to spec §8:** the spec says `freeze_contract.py --check` is "expected clean — no frozen contract changes". That is wrong. Registry schemas *are* frozen (`contract/populations.schema.json` exists), so this plan **adds** `contract/variant_normalization.schema.json`. No existing contract file changes, which is the property that actually matters. Task 1 covers this.
- Run gates from the repo root with the project venv. Note `ruff` is not on `PATH`; use `.venv/bin/ruff`.

---

### Task 1: Schema and frozen contract

**Files:**
- Create: `genomeos/registry/variants.py`
- Modify: `scripts/freeze_contract.py:17-38` (imports and the `PANDERA_SCHEMAS` dict)
- Create: `contract/variant_normalization.schema.json` (generated, committed)
- Test: `tests/test_variant_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `VARIANT_NORMALIZATION_SCHEMA` (a `pa.DataFrameSchema` named `variant_normalization`), the constants `RESOLUTION_STATUSES`, `STRANDS`, and the module-level regex constants `_RSID` and `_NORMALIZED_VARIANT`.

- [ ] **Step 1: Write the failing test**

```python
"""The reviewed variant-normalization registry (design 2026-09-10 §5)."""

from __future__ import annotations

import pandas as pd
import pytest

from genomeos.registry.variants import VARIANT_NORMALIZATION_SCHEMA


def _row(**overrides) -> dict[str, object]:
    """One valid resolved row. Overrides replace individual fields."""
    row = {
        "variant_id": "cyt:example-1-a",
        "status": "resolved",
        "rsid": "rs1",
        "normalized_variant_id": "chr1-100-A-G",
        "printed_alleles": "A/G",
        "printed_convention": "promoter offset -1 from the TSS used by the source",
        "strand": "plus",
        "strand_evidence": "",
        "reference_resource": "dbSNP build 156; Ensembl release 112",
        "naming_citation": "pmid:12345678",
        "resolved_at": "2026-09-10T00:00:00Z",
        "reviewed_by": "human:reviewer",
        "verification_status": "pending",
        "refusal_reason": "",
        "notes": "",
    }
    row.update(overrides)
    return row


def test_a_valid_resolved_row_passes():
    frame = pd.DataFrame([_row()])
    assert len(VARIANT_NORMALIZATION_SCHEMA.validate(frame)) == 1


def test_an_unknown_status_is_refused():
    frame = pd.DataFrame([_row(status="probably")])
    with pytest.raises(Exception):
        VARIANT_NORMALIZATION_SCHEMA.validate(frame)


def test_a_malformed_normalized_identifier_is_refused():
    frame = pd.DataFrame([_row(normalized_variant_id="chr1:100:A:G")])
    with pytest.raises(Exception):
        VARIANT_NORMALIZATION_SCHEMA.validate(frame)


def test_a_duplicate_variant_id_is_refused():
    frame = pd.DataFrame([_row(), _row()])
    with pytest.raises(Exception):
        VARIANT_NORMALIZATION_SCHEMA.validate(frame)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genomeos.registry.variants'`

- [ ] **Step 3: Write minimal implementation**

Create `genomeos/registry/variants.py`:

```python
"""Reviewed variant-normalization registry (design 2026-09-10 §5).

A second, canonical way to name a variant this project already maps: a GRCh38 `chr-pos-ref-alt`
identity with a resolved rsID and strand. It sits *beside* the internal `variant_id` and never
replaces it, so no published identity moves (§3A).

Every row is hand-authored and reviewed. Nothing here resolves a variant automatically, and a
`variant_id` with no row is a refusal at every consumer, never a fallback (§7).
"""

from __future__ import annotations

import pandera.pandas as pa

#: A locus is either resolved to a coordinate, or recorded as unresolvable with a reason. An
#: absent row means "not attempted" — a third state, distinguishable from both (§6).
RESOLUTION_STATUSES: tuple[str, ...] = ("resolved", "unresolved")
STRANDS: tuple[str, ...] = ("plus", "minus")
VERIFICATION_STATUSES: tuple[str, ...] = ("verified", "pending")

_RSID = r"^rs[1-9][0-9]*$"
_NORMALIZED_VARIANT = r"^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|MT)-[1-9][0-9]*-[ACGT]+-[ACGT]+$"
_PRINTED_ALLELES = r"^[ACGT]+/[ACGT]+$"

VARIANT_NORMALIZATION_SCHEMA = pa.DataFrameSchema(
    {
        "variant_id": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False, unique=True),
        "status": pa.Column(str, pa.Check.isin(RESOLUTION_STATUSES), nullable=False),
        # Blank on an unresolved row; the loader enforces that pairing, which pandera cannot.
        "rsid": pa.Column(str, pa.Check.str_matches(rf"{_RSID}|^$"), nullable=False),
        "normalized_variant_id": pa.Column(
            str, pa.Check.str_matches(rf"{_NORMALIZED_VARIANT}|^$"), nullable=False
        ),
        # Always required: it is the input to the round-trip check, so it is kept even on a
        # refused row, where it is often the evidence of *why* the row could not resolve.
        "printed_alleles": pa.Column(str, pa.Check.str_matches(_PRINTED_ALLELES), nullable=False),
        "printed_convention": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "strand": pa.Column(str, pa.Check.str_matches(r"^(?:plus|minus)$|^$"), nullable=False),
        "strand_evidence": pa.Column(str, nullable=False),
        "reference_resource": pa.Column(str, nullable=False),
        "naming_citation": pa.Column(str, nullable=False),
        "resolved_at": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "reviewed_by": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "verification_status": pa.Column(
            str, pa.Check.isin(VERIFICATION_STATUSES), nullable=False
        ),
        "refusal_reason": pa.Column(str, nullable=False),
        "notes": pa.Column(str, nullable=False),
    },
    strict=True,
    coerce=True,
    name="variant_normalization",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Register the schema for freezing**

In `scripts/freeze_contract.py`, add the import beside the existing registry import:

```python
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA
from genomeos.registry.variants import VARIANT_NORMALIZATION_SCHEMA
```

and add one entry to `PANDERA_SCHEMAS`:

```python
    "variant_normalization.schema.json": VARIANT_NORMALIZATION_SCHEMA,
```

- [ ] **Step 6: Generate and verify the contract**

Run: `.venv/bin/python scripts/freeze_contract.py`
Expected: writes `contract/variant_normalization.schema.json`.

Then run: `.venv/bin/python scripts/freeze_contract.py --check`
Expected: `contract up to date`.

Then confirm **no existing contract file changed**:

Run: `git status --short contract/`
Expected: exactly one line, `?? contract/variant_normalization.schema.json`. Any `M` line means an existing contract drifted and the work is wrong — stop and investigate.

- [ ] **Step 7: Commit**

```bash
git add genomeos/registry/variants.py tests/test_variant_registry.py \
        scripts/freeze_contract.py contract/variant_normalization.schema.json
git commit -m "feat(registry): add the variant-normalization schema and freeze its contract"
```

---

### Task 2: Cross-field invariants the schema cannot express

**Files:**
- Modify: `genomeos/registry/variants.py`
- Test: `tests/test_variant_registry.py`

**Interfaces:**
- Consumes: `VARIANT_NORMALIZATION_SCHEMA` from Task 1.
- Produces: `is_palindromic(printed_alleles: str) -> bool`, `complement(alleles: str) -> str`, and `validate_rows(frame: pd.DataFrame) -> pd.DataFrame` which raises `ValueError` on any violation and otherwise returns the validated frame.

This is where the design's real safety lives. Pandera checks columns; these checks are about the *relationship* between columns.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_variant_registry.py`:

```python
from genomeos.registry.variants import complement, is_palindromic, validate_rows


@pytest.mark.parametrize(
    ("alleles", "expected"),
    [("A/T", True), ("T/A", True), ("C/G", True), ("G/C", True), ("A/G", False), ("C/T", False)],
)
def test_palindromic_pairs_are_recognised(alleles, expected):
    """A/T and C/G complement to themselves, so strand cannot be inferred from the letters."""
    assert is_palindromic(alleles) is expected


def test_complement_flips_each_allele():
    assert complement("A/G") == "T/C"


def test_printed_alleles_must_round_trip_under_the_recorded_strand():
    """The central check: a minus-strand row whose letters are already plus-strand is a defect."""
    bad = pd.DataFrame([_row(printed_alleles="A/G", strand="minus", normalized_variant_id="chr1-100-A-G")])
    with pytest.raises(ValueError, match="does not round-trip"):
        validate_rows(bad)


def test_a_minus_strand_row_that_does_round_trip_is_accepted():
    good = pd.DataFrame([_row(printed_alleles="T/C", strand="minus", normalized_variant_id="chr1-100-A-G")])
    assert len(validate_rows(good)) == 1


def test_a_palindromic_resolved_row_requires_strand_evidence():
    """The round-trip has no power here, so something else must establish strand (spec §5)."""
    bad = pd.DataFrame(
        [_row(printed_alleles="G/C", normalized_variant_id="chr1-100-G-C", strand_evidence="")]
    )
    with pytest.raises(ValueError, match="palindromic"):
        validate_rows(bad)


def test_a_palindromic_row_with_strand_evidence_is_accepted():
    good = pd.DataFrame(
        [
            _row(
                printed_alleles="G/C",
                normalized_variant_id="chr1-100-G-C",
                strand_evidence="pmid:12345678 states the minus strand explicitly",
            )
        ]
    )
    assert len(validate_rows(good)) == 1


def test_a_resolved_row_without_a_naming_citation_is_refused():
    bad = pd.DataFrame([_row(naming_citation="")])
    with pytest.raises(ValueError, match="naming_citation"):
        validate_rows(bad)


def test_an_unresolved_row_needs_a_reason_and_no_coordinate():
    missing_reason = pd.DataFrame(
        [_row(status="unresolved", rsid="", normalized_variant_id="", strand="", refusal_reason="")]
    )
    with pytest.raises(ValueError, match="refusal_reason"):
        validate_rows(missing_reason)

    keeps_coordinate = pd.DataFrame(
        [_row(status="unresolved", rsid="", refusal_reason="no candidate rsID found")]
    )
    with pytest.raises(ValueError, match="unresolved"):
        validate_rows(keeps_coordinate)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'complement'`

- [ ] **Step 3: Write minimal implementation**

Append to `genomeos/registry/variants.py`:

```python
import pandas as pd

_COMPLEMENT = str.maketrans({"A": "T", "T": "A", "C": "G", "G": "C"})
_PALINDROMES: tuple[frozenset[str], ...] = (frozenset({"A", "T"}), frozenset({"C", "G"}))


def complement(alleles: str) -> str:
    """`"A/G"` -> `"T/C"`. Each allele independently; the slash is preserved."""
    return alleles.translate(_COMPLEMENT)


def is_palindromic(printed_alleles: str) -> bool:
    """True when complementing returns the same pair, so the letters cannot reveal strand.

    `A/T` and `C/G` are their own complements. For those the round-trip check in `validate_rows`
    passes under *either* strand and therefore proves nothing, which is why such rows are required
    to carry `strand_evidence` instead (design §5).
    """
    return frozenset(printed_alleles.split("/")) in _PALINDROMES


def validate_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Schema validation plus the cross-field invariants pandera cannot express."""
    validated = VARIANT_NORMALIZATION_SCHEMA.validate(frame)
    for row in validated.itertuples():
        where = f"variant_normalization[{row.variant_id}]"
        if row.status == "unresolved":
            if not row.refusal_reason.strip():
                raise ValueError(f"{where}: an unresolved row requires a refusal_reason")
            if row.rsid or row.normalized_variant_id or row.strand:
                raise ValueError(
                    f"{where}: an unresolved row must not carry an rsid, coordinate, or strand"
                )
            continue

        for field in ("rsid", "normalized_variant_id", "strand", "reference_resource"):
            if not str(getattr(row, field)).strip():
                raise ValueError(f"{where}: a resolved row requires {field}")
        if not row.naming_citation.strip():
            raise ValueError(
                f"{where}: a resolved row requires a naming_citation — the source establishing "
                "that the legacy name denotes this rsID. Without one the row is unresolved (§6)."
            )
        if row.refusal_reason.strip():
            raise ValueError(f"{where}: a resolved row must not carry a refusal_reason")

        _, _, ref, alt = row.normalized_variant_id.rsplit("-", 3)
        printed = row.printed_alleles if row.strand == "plus" else complement(row.printed_alleles)
        if frozenset(printed.split("/")) != frozenset({ref, alt}):
            raise ValueError(
                f"{where}: printed_alleles {row.printed_alleles!r} on the {row.strand} strand "
                f"does not round-trip to {{{ref}, {alt}}}"
            )
        if is_palindromic(row.printed_alleles) and not row.strand_evidence.strip():
            raise ValueError(
                f"{where}: {row.printed_alleles!r} is palindromic, so the round-trip cannot "
                "detect a strand error; strand_evidence is required"
            )
    return validated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add genomeos/registry/variants.py tests/test_variant_registry.py
git commit -m "feat(registry): enforce round-trip, palindromic strand evidence, and refusal pairing"
```

---

### Task 3: The loader and the resolution function

**Files:**
- Modify: `genomeos/registry/variants.py`
- Test: `tests/test_variant_registry.py`

**Interfaces:**
- Consumes: `validate_rows` from Task 2.
- Produces: `NormalizedIdentity` (a frozen dataclass with `variant_id: str`, `rsid: str`, `normalized_variant_id: str`, `strand: str`), `load(path: Path) -> pd.DataFrame`, and `normalized_identity(variant_id: str, registry: pd.DataFrame) -> NormalizedIdentity | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_variant_registry.py`:

```python
from pathlib import Path

from genomeos.registry.variants import NormalizedIdentity, load, normalized_identity


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "variant_normalization.tsv"
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)
    return path


def test_load_reads_and_validates(tmp_path):
    registry = load(_write(tmp_path, [_row()]))
    assert list(registry["variant_id"]) == ["cyt:example-1-a"]


def test_load_refuses_an_invalid_file(tmp_path):
    path = _write(tmp_path, [_row(status="resolved", naming_citation="")])
    with pytest.raises(ValueError, match="naming_citation"):
        load(path)


def test_a_resolved_variant_returns_its_identity(tmp_path):
    registry = load(_write(tmp_path, [_row()]))
    assert normalized_identity("cyt:example-1-a", registry) == NormalizedIdentity(
        variant_id="cyt:example-1-a",
        rsid="rs1",
        normalized_variant_id="chr1-100-A-G",
        strand="plus",
    )


def test_an_absent_variant_returns_none(tmp_path):
    """Absence is a refusal for the caller, not a blank to fill (§7)."""
    registry = load(_write(tmp_path, [_row()]))
    assert normalized_identity("cyt:not-in-the-registry", registry) is None


def test_an_unresolved_variant_returns_none(tmp_path):
    """A recorded refusal is consumed exactly like an absent row; the difference is visibility."""
    registry = load(
        _write(
            tmp_path,
            [
                _row(
                    status="unresolved",
                    rsid="",
                    normalized_variant_id="",
                    strand="",
                    naming_citation="",
                    refusal_reason="no candidate rsID in LitVar2 or dbSNP",
                )
            ],
        )
    )
    assert normalized_identity("cyt:example-1-a", registry) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'NormalizedIdentity'`

- [ ] **Step 3: Write minimal implementation**

Append to `genomeos/registry/variants.py` (add `from dataclasses import dataclass` and `from pathlib import Path` to the imports):

```python
@dataclass(frozen=True)
class NormalizedIdentity:
    """A reviewed second name for a variant. Only ever constructed from a `resolved` row."""

    variant_id: str
    rsid: str
    normalized_variant_id: str
    strand: str


def load(path: Path) -> pd.DataFrame:
    """Read and fully validate the registry. Raises rather than returning a partial table."""
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    return validate_rows(frame)


def normalized_identity(variant_id: str, registry: pd.DataFrame) -> NormalizedIdentity | None:
    """The reviewed identity for `variant_id`, or `None` if there is not one.

    `None` covers both "no row" and "recorded as unresolvable". Callers must treat it as a
    refusal — there is no fallback, and in particular no inferring a coordinate from the shape of
    the identifier (§7).
    """
    matches = registry[(registry["variant_id"] == variant_id) & (registry["status"] == "resolved")]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return NormalizedIdentity(
        variant_id=variant_id,
        rsid=row["rsid"],
        normalized_variant_id=row["normalized_variant_id"],
        strand=row["strand"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Run the repo gates**

```bash
.venv/bin/ruff check .
.venv/bin/python scripts/freeze_contract.py --check
.venv/bin/python scripts/check_module_size.py
.venv/bin/python scripts/check_private_files.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add genomeos/registry/variants.py tests/test_variant_registry.py
git commit -m "feat(registry): add the loader and the normalized-identity resolution function"
```

---

### Task 4: The exporter consults the registry

**Files:**
- Modify: `scripts/export_atlas_web.py:419-504` (`_external_resources`)
- Test: `tests/test_export_atlas_web.py`

**Interfaces:**
- Consumes: `normalized_identity` and `load` from Task 3.
- Produces: `_external_resources` gains a keyword-only parameter `variant_registry: pd.DataFrame`.

This replaces the coordinate-shape check requested in review of [#207](https://github.com/bschilder/genomeOS/pull/207). One source of truth instead of a regex in Python and another in TypeScript.

**Before starting**, read the existing `_external_resources` in full. It already refuses when `entity_type != "variant"`, which is what excludes HLA (`allele`) and KIR (`gene`) artifacts. **Do not remove or weaken that check** — this task adds a second, narrower gate for artifacts that *are* typed `variant` but carry a non-coordinate identifier.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export_atlas_web.py`:

```python
def test_a_coordinate_keyed_resource_needs_a_reviewed_normalization(tmp_path):
    """A cytokine locus is entity_type=variant but has a composite id, so it must refuse until
    the registry says otherwise. Previously this passed the exporter and failed in the browser."""
    from genomeos.registry.variants import VARIANT_NORMALIZATION_SCHEMA

    empty = VARIANT_NORMALIZATION_SCHEMA.validate(
        pd.DataFrame(columns=list(VARIANT_NORMALIZATION_SCHEMA.columns))
    )
    entry = {
        "external_resources": [
            {
                "source": "gnomad",
                "normalized_variant_id": "cyt:il-6-174-c",
                "dataset": "gnomad_r4",
                "cache_file": "external/gnomad/cyt.json",
            }
        ]
    }
    with pytest.raises(ValueError, match="no reviewed normalization"):
        export_atlas_web._external_resources(
            entry,
            artifact_id="cyt-il-6-174-c",
            variant_id="cyt:il-6-174-c",
            entity_type="variant",
            source_root=tmp_path,
            out_dir=tmp_path / "out",
            variant_registry=empty,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_export_atlas_web.py -k coordinate_keyed -v`
Expected: FAIL — `TypeError: _external_resources() got an unexpected keyword argument 'variant_registry'`

- [ ] **Step 3: Write minimal implementation**

Add the import at the top of `scripts/export_atlas_web.py`:

```python
from genomeos.registry.variants import normalized_identity
```

Add the parameter to the signature, after `entity_type`:

```python
    variant_registry: pd.DataFrame,
```

and insert this immediately after the existing `entity_type` guard (currently line 432-433):

```python
    # An artifact may be entity_type=variant and still not be a coordinate substitution — the
    # cytokine loci are named by promoter offset. A coordinate-keyed external source can only
    # attach where a reviewed normalization exists, so the registry is the single gate rather
    # than a shape regex duplicated here and in the TypeScript contract (#207 review).
    if declared and normalized_identity(variant_id, variant_registry) is None:
        raise ValueError(
            f"allowlist artifact {artifact_id}: no reviewed normalization for {variant_id}; "
            "add a reviewed row to data/registry/variant_normalization.tsv or remove the "
            "external resource"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_export_atlas_web.py -k coordinate_keyed -v`
Expected: PASS.

- [ ] **Step 5: Update every existing caller and fix the fallout**

Find them: `grep -rn "_external_resources(" scripts/ tests/`

Each caller must now pass `variant_registry=`. The existing HbS tests will fail until the registry contains `chr11-5227002-T-A`; that row is the first one Task 5 writes. Until then, pass a one-row frame built inline in the test fixture so this task stays independently green:

```python
HBS_REGISTRY_ROW = {
    "variant_id": "chr11-5227002-T-A",
    "status": "resolved",
    "rsid": "rs334",
    "normalized_variant_id": "chr11-5227002-T-A",
    "printed_alleles": "T/A",
    "printed_convention": "already a GRCh38 coordinate identity; no legacy naming to resolve",
    "strand": "plus",
    "strand_evidence": "",
    "reference_resource": "identity row; no external resolution required",
    "naming_citation": "identity row; the internal id is already the normalized id",
    "resolved_at": "2026-09-10T00:00:00Z",
    "reviewed_by": "human:bschilder",
    "verification_status": "verified",
    "refusal_reason": "",
    "notes": "Self-identity: the adapter already mints a normalized coordinate for this variant.",
}
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS. Investigate any failure before continuing — a failure here most likely means a caller was missed.

- [ ] **Step 7: Commit**

```bash
git add scripts/export_atlas_web.py tests/test_export_atlas_web.py
git commit -m "feat(atlas): gate coordinate-keyed external resources on a reviewed normalization"
```

---

### Task 5: Seed the registry, and record what will not resolve

**Files:**
- Create: `data/registry/variant_normalization.tsv`
- Create: `docs/audits/variant-normalization-2026-09.md`
- Test: `tests/test_variant_registry.py`

**Interfaces:**
- Consumes: `load` from Task 3.
- Produces: the checked-in registry file.

**This task is different in kind from the others.** It is not code; it is research whose output is reviewed rows. Follow the runbook rather than a TDD cycle, and expect refusals to be a normal outcome rather than a failure.

**Scope:** the HbS identity row, plus the four published cytokine loci — `cyt:il-6-174-c`, `cyt:il-10-1082-g`, `cyt:il-10-819-t`, `cyt:tnfalpha-308-a`. **Not** the other 56 loci (spec §2).

- [ ] **Step 1: For each locus, gather evidence before writing anything**

For each of the four, in order:

1. **Propose** candidate rsIDs using LitVar2, which maps literature mentions to rsIDs and returns citations. It proposes; it never decides.
2. **Resolve independently, twice.** Ensembl Variant Recoder and NCBI dbSNP must return the same GRCh38 placement. **LitVar2 does not count as the second resource** — it is NCBI, so agreeing with dbSNP is not corroboration (spec §5).
3. **Find the naming citation.** Does the candidate's dbSNP record, or LitVar2's trail, cite literature that uses the legacy name (`-174`, `-308`, `-1082`, `-819`)? Record that citation.
4. **Check for palindromy.** `IL-6 -174 G>C` is `G/C` and therefore palindromic — the round-trip will not protect it. It needs explicit `strand_evidence`: a statement of strand in the naming citation or the reference resource, or a flanking-sequence match.

**If any step yields nothing or yields ambiguity, stop and write an `unresolved` row.** That is a correct outcome, not a failure to work around.

- [ ] **Step 2: Write the rows**

Create `data/registry/variant_normalization.tsv`, tab-separated, with the 15 columns from Task 1 in that order. Include the HbS identity row from Task 4 Step 5.

Set `verification_status` to `pending` on every resolved cytokine row. Per spec §9, [#242](https://github.com/bschilder/genomeOS/issues/242) decides whether an agent-resolved row may be agent-verified, and until then nothing promotes to `verified`. Set `reviewed_by` to the identity that actually did the work: `agent:<provider>:<model>` if an agent resolved it.

- [ ] **Step 3: Write the test that pins the file**

```python
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "registry" / "variant_normalization.tsv"


def test_the_committed_registry_validates():
    registry = load(REGISTRY_PATH)
    assert len(registry) >= 1


def test_every_resolved_row_cites_its_naming_source():
    registry = load(REGISTRY_PATH)
    resolved = registry[registry["status"] == "resolved"]
    assert (resolved["naming_citation"].str.strip() != "").all()


def test_every_unresolved_row_states_what_was_attempted():
    registry = load(REGISTRY_PATH)
    unresolved = registry[registry["status"] == "unresolved"]
    assert (unresolved["refusal_reason"].str.strip() != "").all()
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/test_variant_registry.py -v`
Expected: PASS. A round-trip or palindromic failure here means a row is wrong — fix the row, never the check.

- [ ] **Step 5: Write the audit note**

Create `docs/audits/variant-normalization-2026-09.md` recording, for each locus attempted: the candidate considered, both resolutions, the naming citation, the strand evidence where palindromic, and for every refusal what was tried and what returned nothing. State the counts in three states — resolved, refused, not attempted — and make them reconcile against the 60 loci in the corpus.

- [ ] **Step 6: Run every gate, then commit**

```bash
.venv/bin/ruff check .
.venv/bin/python scripts/freeze_contract.py --check
.venv/bin/python scripts/check_module_size.py
.venv/bin/python scripts/check_private_files.py
.venv/bin/python scripts/smoke.py
.venv/bin/python -m pytest
```

Then confirm the acceptance evidence for the whole plan:

```bash
git diff --stat origin/main -- website/public/data/atlas/catalog.json
```

Expected: **empty**. No published identity moved. If this is non-empty, the work is wrong.

```bash
git add data/registry/variant_normalization.tsv tests/test_variant_registry.py \
        docs/audits/variant-normalization-2026-09.md
git commit -m "data(registry): seed reviewed variant normalizations and record refusals"
```

---

### Task 6: Follow through on what this supersedes

**Files:**
- Modify: `docs/literature-evidence-curation.md`
- No code.

Spec §10 lists two consequences that are easy to drop on the floor. Neither is optional.

- [ ] **Step 1: Correct the #207 review**

My review of [#207](https://github.com/bschilder/genomeOS/pull/207) asked the contributor to add a
coordinate-shape check to `_external_resources`. Task 4 supersedes that with a registry lookup.
Post a comment on #207 saying so, so the contributor does not build the weaker version:

```bash
gh pr comment 207 --repo bschilder/genomeOS --body "..."
```

The comment must say what replaced it and why one gate beats two that can drift. Do not let this
wait until #207 is next touched — the contributor may act on the original ask at any time.

- [ ] **Step 2: Cross-reference the two normalization mechanisms**

`docs/literature-evidence-curation.md` documents `variant_normalization` as an allowlisted
derivation for the literature ledger. This registry is the adapter-side counterpart of the same
discipline. Add a short pointer in each direction so a reader who finds one learns the other
exists, and so nobody implements a third mechanism later.

- [ ] **Step 3: Commit**

```bash
git add docs/literature-evidence-curation.md
git commit -m "docs: cross-reference the literature and adapter normalization paths"
```

---

## Verification for the pull request

State each of these with its actual output, not a tick:

- `ruff check .`; `freeze_contract.py --check`; `check_module_size.py`; `check_private_files.py`; `smoke.py`; `pytest`.
- `git diff origin/main -- website/public/data/atlas/catalog.json` is empty — the non-breaking claim.
- `git status --short contract/` shows one added file and no modified ones.
- The registry's three-state counts, reconciling against 60 loci.

Say explicitly which loci refused and why. A PR that resolves fewer than four is a good outcome if the refusals are honest.
