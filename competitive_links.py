#!/usr/bin/env python3
"""Link the competitive set to our own garages.

Writes competitive/links.csv: for each garage in the competitive set that is also
one we hold (and so may have occupancy), the place_id it matches. Run it on the
server, where the database is, and commit the result; rows are reviewed.

A pair matches when the two are within 250 m, their names agree once operator and
"Parkhaus"/"car park" wording is stripped (the closer they are, the less agreement
is needed), and their capacities are within 40% where both are known. Each garage
on either side is used at most once, best pair first -- without that, adjacent
sub-garages (Villa ArenA P4/P5, Riem Arcaden) swap places. Garages that
garage_links.py lists as duplicates of another feed's garage are not candidates,
so a link always points at the canonical one.

Usage: python3 competitive_links.py [out.csv]      (default competitive/links.csv)
"""

from __future__ import annotations

import csv
import difflib
import math
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import competitive
from garage_links import duplicates

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
MAX_M = 250
CAPACITY_TOLERANCE = 0.4
WORDS = (r"\b(parkhaus|tiefgarage|parkgarage|parkplatz|parkdeck|garage|parking|parkeergarage|car ?park|"
         r"q-?park|apcoa|contipark|indigo|interparking|ncp|p\+r|p&r|park ?one|effia|parkbee)\b")


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("ß", "ss")).lower()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", re.sub(WORDS, " ", s))


def metres(lat1, lon1, lat2, lon2) -> float:
    return math.hypot((lat1 - lat2) * 110540, (lon1 - lon2) * 111320 * math.cos(math.radians(lat1)))


def accepted(d: float, sim: float) -> bool:
    return (d <= 60 and sim >= 0.45) or (d <= 150 and sim >= 0.6) or (d <= MAX_M and sim >= 0.8)


def build() -> list[list]:
    dup = set(duplicates())
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ours = [r for r in conn.execute(
        "SELECT place_id, place_name, num_all, latitude, longitude FROM lots_meta "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND num_all IS NOT NULL") if r[0] not in dup]
    conn.close()
    grid: dict[tuple[float, float], list] = {}
    for o in ours:
        grid.setdefault((round(o[3], 2), round(o[4], 2)), []).append(o)
    pairs = []
    for (country, city), gs in competitive.garages().items():
        for g in gs:
            key = (country, city, g["id"])
            for dlat in (-.01, 0, .01):
                for dlon in (-.01, 0, .01):
                    for o in grid.get((round(g["lat"] + dlat, 2), round(g["lon"] + dlon, 2)), []):
                        d = metres(g["lat"], g["lon"], o[3], o[4])
                        if d > MAX_M:
                            continue
                        sim = difflib.SequenceMatcher(None, norm(g["name"]), norm(o[1])).ratio()
                        if not accepted(d, sim):
                            continue
                        if g["capacity"] and o[2] and abs(o[2] - g["capacity"]) / max(o[2], g["capacity"]) > CAPACITY_TOLERANCE:
                            continue
                        pairs.append((sim - d / 2000, key, o, d, sim))
    pairs.sort(key=lambda p: -p[0])
    used_k, used_o, rows = set(), set(), []
    for _, key, o, d, sim in pairs:
        if key in used_k or o[0] in used_o:
            continue
        used_k.add(key); used_o.add(o[0])
        rows.append([*key, o[0], o[1], round(d), round(sim, 2)])
    return sorted(rows)


def main() -> None:
    rows = build()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else competitive.DIR / "links.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["country", "city", "id", "place_id", "place_name", "dist_m", "name_sim"])
        w.writerows(rows)
    total = sum(len(g) for g in competitive.garages().values())
    print(f"{out}: {len(rows)} of {total} competitive garages linked to one of ours", file=sys.stderr)


if __name__ == "__main__":
    main()
