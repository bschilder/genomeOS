"""Local reference-window freeze CLI integration controls (design §§4–8, 12; #254)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_reference_windows.py"
FIXTURES = ROOT / "tests" / "fixtures" / "reference_windows"


def _command(
    out: Path, *, source_metadata: Path | None = None, source_audit: Path | None = None
) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--source-metadata",
        str(source_metadata or FIXTURES / "synthetic-sources.json"),
        "--contigs",
        str(FIXTURES / "synthetic-contigs.txt"),
        "--source-audit",
        str(source_audit or FIXTURES / "synthetic-audit.md"),
        "--data-version",
        "synthetic-reference-v1",
        "--evidence-kind",
        "synthetic_fixture",
        "--out",
        str(out),
    ]


def _run(command: list[str], *, pythonpath: Path = ROOT):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(pythonpath)
    environment["PYTENSOR_FLAGS"] = "base_compiledir=/private/tmp/genomeos-window-pytensor-base"
    environment["MPLCONFIGDIR"] = "/private/tmp/genomeos-window-mpl"
    environment["XDG_CACHE_HOME"] = "/private/tmp/genomeos-window-cache"
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def test_freeze_is_byte_reproducible_and_records_bounded_provenance(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    one = _run(_command(first))
    two = _run(_command(second))

    assert one.returncode == two.returncode == 0, (one.stderr, two.stderr)
    assert sorted(path.name for path in first.iterdir()) == ["manifest.json", "windows.tsv"]
    assert (first / "windows.tsv").read_bytes() == (second / "windows.tsv").read_bytes()
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()

    manifest = json.loads((first / "manifest.json").read_bytes())
    assert manifest["schema_version"] == "reference_windows_v1"
    assert manifest["omitted_source_chromosomes"] == ["chrX", "chrY"]
    assert manifest["contig_evidence"] == "saved_pilot_header_declarations"
    assert manifest["source_evidence_status"] == "supplied_audit_not_reperformed"
    assert manifest["count_contract"] == "pilot_stage_qc_semantics_unchanged_v1"
    assert manifest["publication_eligible"] is False
    assert manifest["p1_eligible"] is False
    assert manifest["provenance"]["evidence_kind"] == "synthetic_fixture"
    assert manifest["provenance"]["source_audit_locator"] == "synthetic-audit.md"
    assert set(manifest["provenance"]["input_sha256"]) == {
        "contigs",
        "selection_config",
        "source_audit",
        "source_metadata",
    }
    assert set(manifest["provenance"]["imported_source_sha256"]) == {
        "genomeos/validation/reference_window_manifest.py",
        "genomeos/validation/reference_window_types.py",
        "genomeos/validation/reference_windows.py",
        "scripts/freeze_reference_windows.py",
    }
    assert len(manifest["provenance"]["source_revision"]) == 40
    assert manifest["windows_sha256"] == hashlib.sha256((first / "windows.tsv").read_bytes()).hexdigest()
    assert manifest["windows_sha256"] == "73cc7af1f6b5b0d3811cf3f659a3ba7cd6173db9c73376227d4d90ce60958032"


def test_existing_output_refuses_without_changing_original_bytes(tmp_path):
    output = tmp_path / "frozen"
    assert _run(_command(output)).returncode == 0
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    repeated = _run(_command(output))

    assert repeated.returncode != 0
    assert "already exists" in repeated.stderr
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_generation_and_raw_input_changes_are_bound_into_manifest(tmp_path):
    original_output = tmp_path / "original"
    assert _run(_command(original_output)).returncode == 0
    original = json.loads((original_output / "manifest.json").read_bytes())

    rows = json.loads((FIXTURES / "synthetic-sources.json").read_bytes())
    old_generation = rows[0]["metadata"]["generation"]
    new_generation = str(int(old_generation) + 1000)
    rows[0]["metadata"]["generation"] = new_generation
    rows[0]["metadata"]["id"] = rows[0]["metadata"]["id"].removesuffix(old_generation) + new_generation
    rows[0]["url"] = rows[0]["url"].removesuffix(old_generation) + new_generation
    changed_path = tmp_path / "changed-sources.json"
    changed_path.write_text(json.dumps(rows))
    changed_output = tmp_path / "changed"

    completed = _run(_command(changed_output, source_metadata=changed_path))

    assert completed.returncode == 0, completed.stderr
    changed = json.loads((changed_output / "manifest.json").read_bytes())
    assert changed["sources"][0]["vcf"]["generation"] == new_generation
    assert (
        changed["provenance"]["input_sha256"]["source_metadata"]
        != original["provenance"]["input_sha256"]["source_metadata"]
    )
    assert (changed_output / "manifest.json").read_bytes() != (original_output / "manifest.json").read_bytes()
    assert (changed_output / "windows.tsv").read_bytes() == (original_output / "windows.tsv").read_bytes()


def test_one_audit_byte_changes_only_the_bound_input_hash(tmp_path):
    original_output = tmp_path / "original"
    assert _run(_command(original_output)).returncode == 0
    original = json.loads((original_output / "manifest.json").read_bytes())
    changed_audit = tmp_path / "synthetic-audit.md"
    changed_audit.write_bytes((FIXTURES / "synthetic-audit.md").read_bytes() + b"\n")
    changed_output = tmp_path / "changed"

    completed = _run(_command(changed_output, source_audit=changed_audit))

    assert completed.returncode == 0, completed.stderr
    changed = json.loads((changed_output / "manifest.json").read_bytes())
    old_hashes = original["provenance"]["input_sha256"]
    new_hashes = changed["provenance"]["input_sha256"]
    assert old_hashes["source_audit"] != new_hashes["source_audit"]
    assert {key: value for key, value in old_hashes.items() if key != "source_audit"} == {
        key: value for key, value in new_hashes.items() if key != "source_audit"
    }


def test_invalid_input_does_not_create_output_directory(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"[]\n")
    output = tmp_path / "frozen"

    completed = _run(_command(output, source_metadata=invalid))

    assert completed.returncode != 0
    assert not output.exists()


def test_oversize_input_refuses_before_output_creation(tmp_path):
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    output = tmp_path / "frozen"

    completed = _run(_command(output, source_metadata=oversized))

    assert completed.returncode != 0
    assert "4 MiB" in completed.stderr
    assert not output.exists()


def test_script_copy_refuses_imports_outside_its_checkout(tmp_path):
    copied_root = tmp_path / "copied"
    copied_script = copied_root / "scripts" / SCRIPT.name
    copied_script.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, copied_script)
    output = tmp_path / "frozen"
    command = _command(output)
    command[1] = str(copied_script)

    completed = _run(command)

    assert completed.returncode != 0
    assert "outside this checkout" in completed.stderr
    assert not output.exists()
