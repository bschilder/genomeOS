"""RunPod launch-boundary tests for MAP spatial support (design §6, §7, §12)."""

from __future__ import annotations

import sys

import pytest

from scripts import runpod_fit


@pytest.mark.parametrize("job", sorted(runpod_fit.HBS_JOBS))
def test_hbs_jobs_refuse_before_a_pod_can_be_created(monkeypatch, job):
    calls = []
    monkeypatch.setattr(runpod_fit, "_request", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(sys, "argv", ["runpod_fit.py", "--job", job, "--launch"])

    with pytest.raises(SystemExit, match="curated CSV with explicit spatial support"):
        runpod_fit.main()

    assert calls == []


def test_non_hbs_plan_remains_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runpod_fit.py", "--job", "gpucheck", "--plan"])

    runpod_fit.main()

    assert "pass --launch to create it" in capsys.readouterr().out
