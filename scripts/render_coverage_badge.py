"""Render the README coverage badge from pytest-cov's JSON report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_README_BADGE = re.compile(r"\[!\[Coverage\]\([^)]*\)\]\([^)]*\)")
_COVERAGE_DESTINATION = "website/public/_static/coverage.svg"


def _colour(percent: int) -> str:
    if percent >= 90:
        return "#4c1"
    if percent >= 80:
        return "#97ca00"
    if percent >= 70:
        return "#a4a61d"
    if percent >= 60:
        return "#dfb317"
    if percent >= 50:
        return "#fe7d37"
    return "#e05d44"


def _shields_colour(percent: int) -> str:
    if percent >= 90:
        return "brightgreen"
    if percent >= 80:
        return "green"
    if percent >= 70:
        return "yellowgreen"
    if percent >= 60:
        return "yellow"
    if percent >= 50:
        return "orange"
    return "red"


def update_readme_badge(readme: Path, percent: int) -> None:
    text = readme.read_text(encoding="utf-8")
    image_url = f"https://img.shields.io/badge/coverage-{percent}%25-{_shields_colour(percent)}.svg"
    badge = f"[![Coverage]({image_url})]({_COVERAGE_DESTINATION})"
    updated, replacements = _README_BADGE.subn(badge, text)
    if replacements != 1:
        raise ValueError(f"{readme}: expected exactly one coverage badge, found {replacements}")
    readme.write_text(updated, encoding="utf-8")


def render_badge(percent: int) -> str:
    value = f"{percent}%"
    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="116" height="20" role="img" '
        f'aria-label="coverage: {value}">\n'
    )
    body = f"""  <title>coverage: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="116" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="75" height="20" fill="#555"/>
    <rect x="75" width="41" height="20" fill="{_colour(percent)}"/>
    <rect width="116" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="37.5" y="15" fill="#010101" fill-opacity=".3">coverage</text>
    <text x="37.5" y="14">coverage</text>
    <text x="94.5" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="94.5" y="14">{value}</text>
  </g>
</svg>
"""
    return header + body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", type=Path, default=Path("coverage.json"))
    parser.add_argument("--out", type=Path, default=Path("website/public/_static/coverage.svg"))
    parser.add_argument("--readme", type=Path)
    args = parser.parse_args()

    report = json.loads(args.coverage_json.read_text())
    percent = round(float(report["totals"]["percent_covered"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_badge(percent))
    if args.readme is None:
        print(f"Wrote {args.out} ({percent}%)")
    else:
        update_readme_badge(args.readme, percent)
        print(f"Wrote {args.out} and updated {args.readme} ({percent}%)")


if __name__ == "__main__":
    main()
