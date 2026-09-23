"""Render the README coverage badge from pytest-cov's JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


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
    args = parser.parse_args()

    report = json.loads(args.coverage_json.read_text())
    percent = round(float(report["totals"]["percent_covered"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_badge(percent))
    print(f"Wrote {args.out} ({percent}%)")


if __name__ == "__main__":
    main()
