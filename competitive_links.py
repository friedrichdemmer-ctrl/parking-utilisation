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

Many of our feeds publish no coordinates at all (Hamburg, Dresden, Bonn, Lübeck,
the Dutch NPR ones: 165 measured garages in cities that also have a price list),
so distance cannot be used for them. For those a second pass matches on name
within the same city, which needs a much better name agreement (NAME_ONLY_SIM)
and, where both are known, capacities within the same tolerance. Rows from that
pass carry dist_m = -1, so a reader can tell how a link was made.

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
NAME_ONLY_SIM = 0.86        # for garages with no coordinates: name agreement alone decides
NAME_ONLY_DIST = -1         # dist_m of a name-only row
WORDS = (r"\b(parkhaus|tiefgarage|parkgarage|parkplatz|parkdeck|garage|parking|parkeergarage|car ?park|"
         r"q-?park|apcoa|contipark|indigo|interparking|ncp|p\+r|p&r|park ?one|effia|parkbee)\b")


# German names compound the facility word onto the place ("Marktgarage",
# "Friedensplatzgarage") where the other side writes it separately or not at
# all, so a trailing one is dropped too -- but only if something is left.
SUFFIXES = ("tiefgarage", "parkgarage", "parkhaus", "parkplatz", "garage", "parking")


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("ß", "ss")).lower()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    out = re.sub(r"[^a-z0-9]+", "", re.sub(WORDS, " ", s))
    for suffix in SUFFIXES:
        if out.endswith(suffix) and len(out) - len(suffix) >= 4:
            return out[: -len(suffix)]
    return out


def strip_city(name: str, city: str) -> str:
    """Drop a city label a feed adds to every garage name, so the name itself is
    left to compare: the Dutch national register writes "Garage Helicon (Den Haag)"
    and Q-Park's rows "DEN HAAG-Binck City Park", where the competitive set has
    plain "Helicon" and "Binck City Park". Only a parenthesised suffix or a
    leading "CITY-" prefix is removed, never the city name inside a name."""
    out = re.sub(r"\s*\(\s*" + re.escape(city) + r"\s*\)\s*$", "", name or "", flags=re.I)
    return re.sub(r"^\s*" + re.escape(city) + r"\s*[-–]\s*", "", out, flags=re.I)


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
    # the same, for the feeds that publish no coordinates -- matched by name below
    no_coords: dict[str, list] = {}
    for r in conn.execute(
            "SELECT place_id, place_name, num_all, city_name FROM lots_meta "
            "WHERE latitude IS NULL AND num_all IS NOT NULL AND city_name IS NOT NULL AND place_name IS NOT NULL"):
        if r[0] not in dup:
            no_coords.setdefault(r[3], []).append(r)
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
    name_pairs = []
    for (country, city), gs in competitive.garages().items():
        for o in no_coords.get(city, []):
            ours_name = norm(strip_city(o[1], city))
            for g in gs:
                sim = difflib.SequenceMatcher(None, norm(g["name"]), ours_name).ratio()
                if sim < NAME_ONLY_SIM:
                    continue
                if g["capacity"] and o[2] and abs(o[2] - g["capacity"]) / max(o[2], g["capacity"]) > CAPACITY_TOLERANCE:
                    continue
                name_pairs.append((sim, (country, city, g["id"]), o, NAME_ONLY_DIST, sim))
    # distance-matched pairs first: a coordinate match is better evidence than a name
    pairs.sort(key=lambda p: -p[0])
    name_pairs.sort(key=lambda p: -p[0])
    used_k, used_o, rows = set(), set(), []
    for _, key, o, d, sim in pairs + name_pairs:
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
