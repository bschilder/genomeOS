"""Harvest AFND allele frequencies directly, rather than reusing a stale redistribution (P1).

    python scripts/fetch_afnd_frequencies.py --out data/raw/afnd_frequencies.tsv

The pipeline previously read frequencies from
[slowkow/allelefrequencies](https://github.com/slowkow/allelefrequencies), whose table was last
built on **2023-03-15**. AFND accepts submissions continuously, so that is three years of new
populations missing, and it makes the corpus depend on a third party's scrape schedule. This
fetches from the source.

**Same two-hop logic as `fetch_afnd.py`, and the same licence position** — AFND publishes none, and
collection proceeds on the assumed-open basis recorded in #117. Deliberately polite: one request at
a time over a single reused connection, every page cached so a re-run costs nothing and an
interrupted run resumes.

**Two parsing traps, both of which silently corrupt rather than raise.**

1. **Do not drop empty cells.** The `% of individuals` column is frequently blank, so filtering
   empty `<td>`s shifts every later column left and reads a sample size as a frequency. Rows are
   parsed positionally with blanks preserved.
2. **Sample sizes carry thousand separators** (`3,732`). Parsing without stripping them yields NaN,
   which is indistinguishable in a report from a genuinely missing value — it cost 27% of the table
   the first time this data was ingested.

Loci are read from the search form's own `<select>` rather than hard-coded, so a locus AFND adds
later is picked up instead of silently omitted.

**Alleles come at full resolution** (`A*02:17:02:01`), not the two-field form the previous
redistribution used. `hla_level` did not change what the server returned, so rather than depend on
a parameter whose effect is unclear this takes everything and leaves the choice downstream:
summing `A*02:01:01` and `A*02:01:02` within a population gives the two-field frequency, and the
reverse is not recoverable. Two-field is what the spatial models want — it is what gives
`DQB1*03:01` its 471 populations — but that is an aggregation, not a fetch.
"""

from __future__ import annotations

import argparse
import html
import http.client
import re
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

BASE = "www.allelefrequencies.net"
USER_AGENT = "genomeOS-registry/0.1 (+https://github.com/bschilder/genomeOS; research use)"

#: Each group's search endpoint and the query parameter naming its locus.
GROUPS: dict[str, tuple[str, str]] = {
    "hla": ("/hla6006a.asp", "hla_locus"),
    "kir": ("/kir6002a.asp", "kir_locus"),
    "cyt": ("/cyt6001a.asp", "cyt_locus"),
}

COLUMNS = ("group", "gene", "allele", "population", "indivs_over_n", "alleles_over_2n", "n",
           "retrieved_at")


class Session:
    """One HTTPS connection, reused. Opening ~1,200 of them would cost the server far more than
    it costs us; see the note in `fetch_afnd.py`."""

    def __init__(self, timeout: int) -> None:
        self.timeout, self._conn = timeout, None

    def get(self, path: str) -> str:
        for attempt in range(3):
            try:
                if self._conn is None:
                    self._conn = http.client.HTTPSConnection(BASE, timeout=self.timeout)
                self._conn.request("GET", path, headers={"User-Agent": USER_AGENT,
                                                         "Connection": "keep-alive"})
                response = self._conn.getresponse()
                body = response.read()
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                return body.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - retried; a dead connection must not poison the run
                if self._conn is not None:
                    self._conn.close()
                self._conn = None
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("unreachable")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()


def loci_for(body: str, param: str) -> list[str]:
    """The locus list from the form's own <select>, so a newly added locus is not omitted."""
    match = re.search(rf'<select[^>]*name=["\']?{param}["\']?[^>]*>(.*?)</select>', body,
                      re.S | re.I)
    if not match:
        return []
    return [html.unescape(v).strip()
            for v in re.findall(r'<option[^>]*value=["\']([^"\']*)["\']', match.group(1))
            if v.strip()]


def last_page(body: str, endpoint: str) -> int:
    pages = re.findall(rf'{re.escape(endpoint.lstrip("/"))}\?page=(\d+)', body)
    return max((int(p) for p in pages), default=1)


#: Column positions in a results row, verified against a real page rather than assumed:
#:   [0] line  [1] allele  [2] blank  [3] population  [4] % of individuals
#:   [5] allele frequency  [6] blank  [7] sample size  [8] IMGT link
#: The two blanks are the trap. An earlier version filtered empty cells and read `[1:6]`, which
#: shifted every column left, dropped the sample size entirely, and wrote the retrieval date into
#: it. Nothing raised; the output was simply wrong.
_COL = {"allele": 1, "population": 3, "indivs": 4, "af": 5, "n": 7}

#: AFND annotates estimates it considers provisional with a trailing `(*)`. The marker is stripped
#: from the value; it is not a missing value and the row is kept.
_MARKER = re.compile(r"\s*\(\*\)\s*$")


def parse_rows(body: str) -> list[tuple[str, str, str, str, str]]:
    """(allele, population, indivs_over_n, alleles_over_2n, n) per data row."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) <= _COL["n"] or not cells[0].isdigit():
            continue
        value = {k: _MARKER.sub("", cells[i]) for k, i in _COL.items()}
        if not value["allele"] or not value["population"]:
            continue
        out.append((value["allele"], value["population"], value["indivs"], value["af"],
                    value["n"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw/afnd_freq_cache"))
    ap.add_argument("--delay", type=float, default=0.25)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--groups", nargs="*", default=list(GROUPS))
    ap.add_argument("--max-pages", type=int, help="cap per locus, for a trial run")
    args = ap.parse_args()

    args.cache.mkdir(parents=True, exist_ok=True)
    session = Session(args.timeout)
    retrieved = datetime.now(UTC).date().isoformat()
    rows: list[tuple[str, ...]] = []

    def page(path: str, key: str) -> str:
        cached = args.cache / f"{key}.html"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        body = session.get(path)
        cached.write_text(body, encoding="utf-8")
        time.sleep(args.delay)
        return body

    for group in args.groups:
        endpoint, param = GROUPS[group]
        first = page(endpoint, f"{group}_form")
        loci = loci_for(first, param)
        print(f"{group}: {len(loci)} loci -> {loci}", flush=True)
        for locus in loci:
            query = urllib.parse.urlencode({param: locus})
            head = page(f"{endpoint}?{query}", f"{group}_{locus}_p1")
            total = last_page(head, endpoint)
            if args.max_pages:
                total = min(total, args.max_pages)
            found = 0
            for number in range(1, total + 1):
                body = head if number == 1 else page(
                    f"{endpoint}?page={number}&{query}", f"{group}_{locus}_p{number}"
                )
                for allele, population, indiv, af, n in parse_rows(body):
                    rows.append((group, locus, allele, population, indiv, af, n, retrieved))
                    found += 1
            print(f"  {group}/{locus}: {total} pages, {found} rows", flush=True)

    session.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as stream:
        stream.write("\t".join(COLUMNS) + "\n")
        for row in rows:
            stream.write("\t".join(str(c).replace("\t", " ") for c in row) + "\n")
    print(f"\nwrote {args.out}: {len(rows):,} rows")


if __name__ == "__main__":
    main()
