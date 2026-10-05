"""Garages that appear under more than one place_id.

Several cities reach us through two feeds that cover the same garages --
FFH and the city's mainziel feed in Frankfurt, two archive sources in
Mannheim and Wiesbaden, the city feed and the national NPR feed in
Amsterdam -- so the same garage was counted twice in city and country
figures. garage_links/*.csv lists each duplicate place_id with the
canonical place_id it repeats, and the evidence (usually that the two report
the same free counts at the same moments: correlation >= 0.95 over hundreds
of paired readings). Rows are reviewed by hand before they are added.

Reports drop the duplicate and keep the canonical garage. For the trends,
any readings the duplicate has from before the canonical garage's first
reading are folded into it, so a garage that moved from one feed to another
keeps one continuous history. Feeds themselves are untouched: both place_ids
keep collecting, and feed health and alerts still watch both.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

LINKS_DIR = Path(__file__).resolve().parent / "garage_links"


@lru_cache(maxsize=1)
def duplicates() -> dict[str, str]:
    """{duplicate place_id: canonical place_id}"""
    links = {}
    for path in sorted(LINKS_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                links[row["place_id"]] = row["canonical_id"]
    return links


def members() -> dict[str, list[str]]:
    """{canonical place_id: [duplicate place_ids]}"""
    out: dict[str, list[str]] = {}
    for dup, canon in duplicates().items():
        out.setdefault(canon, []).append(dup)
    return out
