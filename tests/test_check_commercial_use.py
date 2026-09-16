"""The commercial-use gate and the extraction inventory it produces.

genomeOS may publish non-commercial-licensed data. What it may not do is publish it unmarked,
because an unmarked field is invisible to anyone trying to pull it back out. These tests pin the
gate that enforces the marking and the listing that turns the markings into an extraction plan.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_commercial_use

ALPHAGENOME_TERMS = "https://deepmind.google.com/science/alphagenome/terms"


def _restricted() -> dict[str, object]:
    return {
        "finding": "restricted",
        "restricted_fields": ["top_attributions"],
        "checked_at": "2026-09-10",
        "terms_url": ALPHAGENOME_TERMS,
        "recorded_in": "docs/audits/alphagenome-avi-licensing.md",
    }


def _write(path: Path, commercial_use: object, *, omit: bool = False) -> None:
    resource: dict[str, object] = {
        "source": "alphagenome",
        "cache_file": "external/alphagenome/chr11-5227002-t-a.json",
    }
    if not omit:
        resource["commercial_use"] = commercial_use
    path.write_text(
        json.dumps({"artifacts": [{"id": "hbs-rs334", "external_resources": [resource]}]})
    )


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    allowlist = tmp_path / "public-artifacts.json"
    catalog = tmp_path / "catalog.json"
    monkeypatch.setattr(check_commercial_use, "ALLOWLIST", allowlist)
    monkeypatch.setattr(check_commercial_use, "CATALOG", catalog)
    return {"allowlist": allowlist, "catalog": catalog}


def test_the_real_repository_passes_the_gate() -> None:
    """The committed allowlist and catalog are marked, and agree with each other."""
    assert check_commercial_use.main([]) == 0


def test_the_real_repository_lists_every_known_restriction(capsys: pytest.CaptureFixture) -> None:
    """`--list` is the extraction plan, so it must name the tripwire fields even when none ship."""
    assert check_commercial_use.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "alphagenome: top_attributions" in out
    assert "gnomad: spliceai" in out


def test_gate_refuses_a_resource_with_no_declaration(files: dict[str, Path]) -> None:
    _write(files["allowlist"], None, omit=True)
    assert check_commercial_use.main([]) == 1


def test_gate_refuses_a_restricted_finding_that_names_nothing(files: dict[str, Path]) -> None:
    declaration = _restricted() | {"restricted_fields": []}
    _write(files["allowlist"], declaration)
    assert check_commercial_use.main([]) == 1


def test_gate_refuses_a_performed_check_with_no_evidence(files: dict[str, Path]) -> None:
    _write(files["allowlist"], {"finding": "explicitly_open", "restricted_fields": []})
    assert check_commercial_use.main([]) == 1


def test_gate_refuses_not_checked_carrying_evidence_fields(files: dict[str, Path]) -> None:
    """`not_checked` means nobody looked, so a terms URL beside it is a contradiction."""
    _write(
        files["allowlist"],
        {"finding": "not_checked", "restricted_fields": [], "terms_url": ALPHAGENOME_TERMS},
    )
    assert check_commercial_use.main([]) == 1


def test_gate_accepts_not_checked_on_its_own(files: dict[str, Path]) -> None:
    """An unperformed check must stay publishable, or contributors will invent findings."""
    _write(files["allowlist"], {"finding": "not_checked", "restricted_fields": []})
    assert check_commercial_use.main([]) == 0


def test_gate_catches_a_catalog_that_shipped_a_different_marking(files: dict[str, Path]) -> None:
    """A stale export is how a restriction silently disappears from the published data."""
    _write(files["allowlist"], _restricted())
    _write(files["catalog"], {"finding": "not_checked", "restricted_fields": []})
    assert check_commercial_use.main([]) == 1


def test_inventory_reports_restricted_fields_and_unchecked_sources(files: dict[str, Path]) -> None:
    _write(files["allowlist"], _restricted())
    restricted, unresolved = check_commercial_use.inventory()
    assert len(restricted) == 1
    assert "record.top_attributions" in restricted[0]
    assert unresolved == []

    _write(files["allowlist"], {"finding": "not_checked", "restricted_fields": []})
    restricted, unresolved = check_commercial_use.inventory()
    assert restricted == []
    assert len(unresolved) == 1


def test_gate_refuses_not_checked_that_names_restricted_fields(files: dict[str, Path]) -> None:
    """The two gates must agree. The exporter refuses this, so the script has to as well.

    A declaration that claims nobody read the terms while naming the fields those terms restrict is
    self-contradictory, and letting one gate accept what the other rejects is how a marking ends up
    meaning different things in CI and at export time.
    """
    _write(
        files["allowlist"],
        {"finding": "not_checked", "restricted_fields": ["top_attributions"]},
    )
    assert check_commercial_use.main([]) == 1
