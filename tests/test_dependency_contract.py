from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


def test_surface_dependencies_exclude_numpy_without_row_stack():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    requirements = {}
    for value in project["project"]["optional-dependencies"]["surfaces"]:
        requirement = Requirement(value)
        requirements[requirement.name] = requirement

    numpy = requirements["numpy"]
    assert Version("2.4.6") in numpy.specifier
    assert Version("2.5.2") not in numpy.specifier
