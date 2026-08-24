from __future__ import annotations

from dataclasses import dataclass


class RegionQueryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Region:
    chromosome: str
    start: int
    end: int

    @classmethod
    def parse(cls, value: str) -> "Region":
        try:
            chromosome, interval = value.split(":", 1)
            start, end = (int(part.replace(",", "")) for part in interval.split("-", 1))
        except (ValueError, AttributeError) as exc:
            raise ValueError("region must look like 1:1000-2000") from exc
        if not chromosome or start < 1 or end < start:
            raise ValueError("invalid genomic region")
        return cls(chromosome, start, end)


class TabixRegionReader:
    """Bounded remote/local Tabix reader; pysam remains an optional dependency."""

    def fetch(self, uri: str, region: Region, *, limit: int) -> list[dict[str, str]]:
        try:
            import pysam
        except ImportError as exc:
            raise RegionQueryUnavailable("install genomeos[tabix] to query regions") from exc
        rows: list[dict[str, str]] = []
        with pysam.TabixFile(uri) as tabix:
            header = [line.lstrip("#") for line in tabix.header]
            columns = header[-1].split("\t") if header else []
            for line in tabix.fetch(region.chromosome, region.start - 1, region.end):
                values = line.split("\t")
                rows.append(dict(zip(columns, values)) if columns else {"raw": line})
                if len(rows) >= limit:
                    break
        return rows
