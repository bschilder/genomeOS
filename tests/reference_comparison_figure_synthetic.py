"""Generate tiny synthetic publications for the paired reporting demonstration.

No fits are run: the existing synthetic fixture supplies hand-set diagnostics.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from reference_comparison_synthetic import publication, refresh

from genomeos.validation.reference_b0h_artifacts import json_bytes


def write_example_inputs(base: Path) -> Path:
    """Write all24 requested identities, including one deliberately absent pair."""
    base.mkdir(parents=True, exist_ok=False)
    records = []
    for stage, kind, seed, rho in itertools.product(
        ("technical_qc_4117", "paper_ancestry_exclusion_4094"),
        ("called", "quality"),
        (42, 43, 44),
        (9, 4),
    ):
        identity = dict(cohort_stage=stage, count_kind=kind, seed=seed, rho_prior_beta=rho)
        paths = {
            "b0_directory": f"synthetic/b0/{stage}/{kind}/{seed}",
            "b0h_directory": f"synthetic/b0h/{stage}/{kind}/{seed}/{rho}",
        }
        for side, relative in paths.items():
            directory = base / relative
            heterogeneity = side == "b0h_directory"
            if directory.exists() or (
                heterogeneity
                and (stage, kind, seed, rho) == ("paper_ancestry_exclusion_4094", "quality", 44, 4)
            ):
                continue
            failed = ()
            if heterogeneity and kind == "quality" and seed == 42:
                failed = (4,)
            if heterogeneity and stage == "paper_ancestry_exclusion_4094" and seed == 43 and rho == 4:
                failed = tuple(range(5))
            log_score = -1.0
            if (not heterogeneity and seed == 43) or (heterogeneity and seed == 44):
                log_score = float("-inf")
            if heterogeneity and seed == 43 and rho == 4:
                log_score = float("-inf")
            files = publication(heterogeneity=heterogeneity, failed=failed, rho=rho, log_score=log_score)
            manifest = json.loads(files["manifest.json"])
            manifest["configuration"].update(cohort_stage=stage, count_kind=kind, seed=seed)
            manifest["seeds"]["root"] = seed
            files["manifest.json"] = json_bytes(manifest)
            splits = json.loads(files["splits.json"])
            splits["configuration"] = manifest["configuration"]
            refresh(files, "splits.json", json_bytes(splits))
            directory.mkdir(parents=True)
            for name, data in files.items():
                (directory / name).write_bytes(data)
        records.append({**identity, **paths})
    path = base / "pairs.json"
    path.write_bytes(json_bytes(dict(schema_version=1, pairs=records)))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    print(write_example_inputs(parser.parse_args().out))
