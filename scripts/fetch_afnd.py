"""Harvest AFND population metadata into the TSV `registry.sources.afnd` consumes (P0, #18).

    python scripts/fetch_afnd.py --out data/raw/afnd_populations.tsv

**Licence status — read before using the output.** AFND publishes no licence. The footer's
"Licensing" link resolves to a page carrying only a disclaimer and a privacy policy, and pages are
marked "©2003-2026 The Allele Frequency Net Database". re3data records the repository as public
domain, but that is third-party catalogue metadata, not a grant. This script exists because the
project owner decided on 2026-08-26 to proceed on an assumed-open basis (#117). **That assumption
is recorded here rather than in someone's memory so it can be revisited**, and it governs
redistribution as much as collection — #66 still applies to anything derived from this data.

**Two hops, both public.** An earlier investigation concluded this data was behind a login. It is
not: the "Access Denied" string that conclusion rested on sits inside an HTML comment, an inert
login template present on every page.

1. ``pop6001b.asp`` — one request, no query, lists every population as a
   ``pop6001c.asp?pop_name=...`` link.
2. ``pop6001c.asp?pop_name=<name>`` — the population page, which prints the coordinate and the
   ascertainment fields.

``pop_name`` is the accession rather than the numeric ``pop_id``, because it is the key AFND's own
public navigation uses, it is the only one obtainable without paginating every locus, and it is
the key the published frequency redistributions are already keyed on — so frequencies and
coordinates join exactly, with no fuzzy name matching.

**Deliberately polite, and resumable.** One request at a time with a delay between them; every
page cached to disk so a re-run costs nothing and an interrupted run resumes. This fetches ~1,800
small pages from a public academic server, and there is no reason to do it quickly.

It does reuse **one connection** for all of them, which is politeness rather than haste: measured
cold, a single page took 48 s and was dominated by TLS setup, while two pages over one connection
took 5.8 s total. Opening 1,800 separate connections would cost the server far more than it costs
us, and would take hours for no benefit.

**Author e-mail addresses are on these pages and are not collected.** They are personal data,
irrelevant to a population registry, and there is no reason to hold them.
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

BASE = "https://www.allelefrequencies.net"
LIST_URL = f"{BASE}/pop6001b.asp"
PAGE_URL = BASE + "/pop6001c.asp?pop_name={name}"

#: Identifies the fetcher to the server. A scraper that hides what it is gives an operator no way
#: to contact anyone or to rate-limit it specifically, which is worse for them and for us.
USER_AGENT = "genomeOS-registry/0.1 (+https://github.com/bschilder/genomeOS; research use)"

#: AFND's own field labels on a population page, mapped to the adapter's column names.
FIELDS = {
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Family": "family",
    "Urban/Rural": "urban_rural",
    "Source": "sample_source",
    "Ethnic origin": "ethnic_origin",
    "Geographic Region": "geographic_region",
    "Sample Size": "sample_size",
    "Test date": "test_date",
}
COLUMNS = (
    ["pop_id", "population"]
    + list(FIELDS.values())
    + ["source_url", "retrieved_at"]
)


class Session:
    """One HTTPS connection, reused. `http.client` keeps it alive across requests provided each
    response body is read fully; it is reopened transparently if the server drops it."""

    def __init__(self, host: str, timeout: int) -> None:
        self.host, self.timeout = host, timeout
        self._connection: http.client.HTTPSConnection | None = None

    def _connect(self) -> http.client.HTTPSConnection:
        if self._connection is None:
            self._connection = http.client.HTTPSConnection(self.host, timeout=self.timeout)
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def get(self, path: str) -> str:
        try:
            connection = self._connect()
            connection.request("GET", path, headers={"User-Agent": USER_AGENT,
                                                     "Connection": "keep-alive"})
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status} for {path}")
            return body.decode("utf-8", errors="replace")
        except Exception:
            self.close()  # a broken connection must not poison every later request
            raise


def _get(session: Session, url: str, cache: Path, *, timeout: int, delay: float,
         attempts: int = 3) -> str:
    """Fetch a URL, caching the body. A cached page costs nothing and is not re-requested.

    Retried with backoff: the listing page is 1.3 MB from an academic server and times out often
    enough that a single attempt makes the run flaky rather than the server unreliable.
    """
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            body = session.get(urllib.parse.urlsplit(url).path
                               + ("?" + urllib.parse.urlsplit(url).query
                                  if urllib.parse.urlsplit(url).query else ""))
            cache.write_text(body, encoding="utf-8")
            time.sleep(delay)
            return body
        except Exception as error:  # noqa: BLE001 - retried below, re-raised if it never succeeds
            last = error
            time.sleep(delay * (attempt + 2) * 2)
    raise RuntimeError(f"{url}: failed after {attempts} attempts ({last})")


def population_names(body: str) -> list[str]:
    """Every population name linked from the listing page, deduplicated and ordered."""
    found = re.findall(r"pop6001c\.asp\?pop_name=([^\"'&>]{1,80})", body)
    return sorted({html.unescape(name).strip() for name in found if name.strip()})


def slugify(name: str) -> str:
    """AFND's population name -> a registry accession.

    `POPULATIONS_SCHEMA` requires `population_id` to match `^[a-z0-9]+(?:[._-][a-z0-9]+)*$`, so
    the name cannot be the accession verbatim. The full name is not lost: it goes to the aliases
    table, which is what that table is for.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", slug)


def parse_population(body: str) -> dict[str, str]:
    """AFND's labelled fields, as printed.

    Coordinates are kept in the printed sexagesimal form: the adapter derives a coordinate
    precision floor from how many places were printed, and converting to decimal here would throw
    that away before it could be read.
    """
    record: dict[str, str] = {}
    for label, value in re.findall(r"<b>([^<]{2,40}?):</b>\s*</td>\s*<td[^>]*>(.*?)</td>", body, re.S):
        key = FIELDS.get(label.strip())
        if key is None:
            continue  # includes Author's e-mail, which is deliberately not collected
        cleaned = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()
        if cleaned and cleaned != "..":
            record[key] = cleaned
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw/afnd_cache"))
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between live requests")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--limit", type=int, help="stop after N populations (for a trial run)")
    args = ap.parse_args()

    session = Session(urllib.parse.urlsplit(BASE).netloc, args.timeout)
    listing = _get(session, LIST_URL, args.cache / "_listing.html",
                   timeout=args.timeout, delay=args.delay)
    names = population_names(listing)
    if args.limit:
        names = names[: args.limit]
    print(f"{len(names)} populations listed")

    retrieved = datetime.now(UTC).date().isoformat()
    rows, failures, seen = [], [], {}
    for index, name in enumerate(names, 1):
        quoted = urllib.parse.quote(name)
        url = PAGE_URL.format(name=quoted)
        cache_key = re.sub(r"[^A-Za-z0-9]+", "_", name)[:80]
        try:
            body = _get(session, url, args.cache / f"{cache_key}.html",
                        timeout=args.timeout, delay=args.delay)
        except Exception as error:  # noqa: BLE001 - one bad page must not end a 1,800-page run
            failures.append((name, f"{type(error).__name__}: {error}"))
            continue
        record = parse_population(body)
        if "latitude" not in record or "longitude" not in record:
            failures.append((name, "no coordinate printed"))
            continue
        slug = slugify(name)
        if slug in seen:
            # Two names slugging to one accession would collide in a unique-keyed table. Suffix
            # rather than drop: a lost population is worse than an ugly id, and it is visible.
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 1
        record.update(pop_id=slug, population=name, source_url=url, retrieved_at=retrieved)
        rows.append(record)
        if index % 100 == 0:
            print(f"  {index}/{len(names)}  kept {len(rows)}  failed {len(failures)}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as stream:
        stream.write("\t".join(COLUMNS) + "\n")
        for record in rows:
            stream.write("\t".join(str(record.get(c, "")).replace("\t", " ") for c in COLUMNS) + "\n")

    session.close()
    print(f"\nwrote {args.out}: {len(rows)} populations, {len(failures)} not usable")
    for name, why in failures[:15]:
        print(f"  {name[:44]:<44} {why}")
    if len(failures) > 15:
        print(f"  ... and {len(failures) - 15} more")


if __name__ == "__main__":
    main()
