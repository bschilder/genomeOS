"""Negative tests for the reference-window guarantees that nothing was falsifying (#299).

Three checks in this stack were load-bearing and untested. Each was confirmed by deleting it and
watching the whole focused suite stay green:

- the comparison of a natively computed allele count against an independently parsed one, which is
  the headline safety claim of the acquisition and preparation boundary;
- the requirement that a manifest account for the complete frozen window set;
- the completeness flag, which gates the entire preparation phase and both command-line exit codes.

A check no test can falsify is a check that silently stops working at the next refactor. Every test
here is written so that removing the production check it covers makes it fail.

The allele-count test deserves a note on why the gap survived. The end-to-end tests replace the
native counter with a stand-in whose totals are derived from the same fake genotype stream they are
compared against, so the two can never disagree. A fake cannot falsify a comparison it was built
from. This test therefore perturbs the parsed total at the seam where it enters the comparison,
leaving the rest of the real path intact.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.test_reference_window_clis import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    _acquisition_composition,
    _cohort,
    _install_acquisition_adapters,
    _install_preparation_adapters,
    _preparation_composition,
    _synthetic_cohort_inputs,
    _synthetic_inputs,
    compose_acquisition,
    compose_preparation,
    count_execution,
    validate_acquisition,
)


def _prepared(tmp_path, monkeypatch):
    """Run acquisition and preparation over one retained SNP, returning the manifest."""
    import json

    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    source_samples = _synthetic_cohort_inputs().source_samples
    _install_acquisition_adapters(
        monkeypatch, retained_window="chr1-s1", source_samples=source_samples
    )
    acquisition_inputs = _acquisition_composition(tmp_path)
    compose_acquisition(acquisition_inputs)
    validate_acquisition(tmp_path / "out", cohort_inputs=acquisition_inputs.cohort)

    frozen = json.loads((tmp_path / "windows" / "manifest.json").read_bytes())
    start0 = next(v["start0"] for v in frozen["windows"] if v["window_id"] == "chr1-s1")
    _install_preparation_adapters(
        monkeypatch,
        technical=_cohort(TECHNICAL_STAGE, 4_117),
        paper=_cohort(PAPER_STAGE, 4_094),
        retained_variant=f"GRCh38:chr1:{start0 + 1}:A:G",
    )
    return _preparation_composition(tmp_path)


def test_a_disagreeing_native_allele_count_refuses_the_window(tmp_path, monkeypatch):
    """The headline claim: two independent counts of the same bytes must agree, or the window goes.

    Deleting the comparison leaves every other focused test passing, because no existing test ever
    supplies a total that disagrees. This one does, and asserts the refusal reaches the ledger with
    its reason intact rather than merely that something failed.
    """
    from scripts import reference_count_replay

    inputs = _prepared(tmp_path, monkeypatch)
    original = count_execution.iter_native_totals

    def disagreeing(*args, **kwargs):
        for total in original(*args, **kwargs):
            if total is None:
                yield total
            else:
                variant_id, called_ac, called_an = total
                yield (variant_id, called_ac + 1, called_an)

    # The comparison exists twice: once on the preparation path and once in the deep replay that
    # confirms a refusal reproduces. Patching only the first makes the refusal fail to reproduce,
    # which is a different error and would hide whether the comparison itself has any power.
    monkeypatch.setattr(count_execution, "iter_native_totals", disagreeing)
    monkeypatch.setattr(reference_count_replay, "iter_native_totals", disagreeing)

    result = compose_preparation(inputs)

    assert result.status == "refused"
    assert result.complete is False
    refused = [window for window in result.windows if window.state == "refused"]
    assert [window.window_id for window in refused] == ["chr1-s1"]
    assert {window.reason for window in refused} == {"native_mismatch"}


def test_an_agreeing_native_allele_count_still_prepares(tmp_path, monkeypatch):
    """The control for the test above, and it is not optional.

    Without it, a refusal caused by something unrelated to the allele counts would look exactly
    like the check working. The same fixture and the same run must succeed when nothing is
    perturbed, or the test above proves nothing about the comparison.
    """
    inputs = _prepared(tmp_path, monkeypatch)
    result = compose_preparation(inputs)

    assert result.complete is True
    assert len(result.windows) == 66
    assert [window for window in result.windows if window.state == "refused"] == []


@pytest.mark.parametrize(
    "mutate, label",
    [
        (lambda windows: windows[:-1], "a missing window"),
        (lambda windows: windows + (windows[-1],), "a duplicated window"),
        (lambda windows: (windows[1], windows[0]) + windows[2:], "a reordered window set"),
    ],
)
def test_acquisition_refuses_an_incomplete_window_set(mutate, label):
    """All 66 windows, in their frozen order. The count alone was the only thing checked before."""
    from tests.test_reference_window_artifacts import refused_acquisition

    manifest = refused_acquisition()
    with pytest.raises(ValueError, match="frozen 66 IDs"):
        replace(manifest, windows=mutate(manifest.windows))


def test_acquisition_refuses_a_completeness_flag_that_disagrees_with_its_receipts():
    """`complete` gates the whole preparation phase and both exit codes, and is never recomputed.

    It is a plain boolean rather than a constrained literal, so decoding does not catch it either.
    This check is the only thing standing between a refused acquisition and a success report.
    """
    manifest = refused = None
    from tests.test_reference_window_artifacts import refused_acquisition

    refused = refused_acquisition()
    assert refused.complete is False, "the fixture must start as a refusal for this to mean anything"
    with pytest.raises(ValueError, match="completeness disagrees"):
        manifest = replace(refused, complete=True)
    assert manifest is None


def test_preparation_refuses_an_incomplete_window_set(tmp_path, monkeypatch):
    """The same frozen-set requirement on the preparation side, which has its own copy of it."""
    inputs = _prepared(tmp_path, monkeypatch)
    result = compose_preparation(inputs)
    with pytest.raises(ValueError, match="frozen 66 IDs"):
        replace(result, windows=result.windows[:-1])
