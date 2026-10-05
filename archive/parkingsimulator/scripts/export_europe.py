"""Merge every city CSV wired into app.py into one Europe-wide file.

Run from the repo root: python scripts/export_europe.py
Writes export/european_parking.csv and export/README.md.
"""
import csv
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
OUT_DIR = os.path.join(ROOT, "export")

COLUMNS = ["id", "name", "operator", "lat", "lon", "capacity", "hourly_rate",
           "daily_cap", "has_ev", "address", "source_url"]
CURRENCY = {"Germany": "EUR", "Netherlands": "EUR", "Ireland": "EUR", "Belgium": "EUR",
            "France": "EUR", "UK": "GBP", "Denmark": "DKK"}

dir_map = {}
country = None
entries = []
for line in open(APP, encoding="utf-8"):
    m = re.match(r'^(\w+_DIR) = os\.path\.join\((\w+), "(\w+)"\)', line)
    if m:
        dir_map[m.group(1)] = m.group(3)
    m = re.match(r'^DATA_DIR = ', line)
    if m:
        dir_map["DATA_DIR"] = ""
    m = re.match(r'^    "([^"]+)": \{$', line)
    if m:
        country = m.group(1)
        continue
    m = re.match(r'^        "([^"]+)": os\.path\.join\((\w+), "([^"]+\.csv)"\)', line)
    if m and country:
        entries.append((country, m.group(1), m.group(2), m.group(3)))

frames = []
for country, city, dirvar, fname in entries:
    sub = dir_map.get(dirvar, "")
    path = os.path.join(ROOT, "data", "cities", sub, fname) if sub else os.path.join(ROOT, "data", fname)
    df = pd.read_csv(path)[COLUMNS]
    df.insert(0, "city", city)
    df.insert(0, "country", country)
    df["currency"] = CURRENCY[country]
    frames.append(df)

out = pd.concat(frames, ignore_index=True)
out["capacity"] = out["capacity"].astype("Int64")
os.makedirs(OUT_DIR, exist_ok=True)
out.to_csv(os.path.join(OUT_DIR, "european_parking.csv"), index=False, quoting=csv.QUOTE_MINIMAL)

readme = f"""# European parking dataset

{len(out)} garages, {out[['country', 'city']].drop_duplicates().shape[0]} cities, {out['country'].nunique()} countries.
Source: https://github.com/friedrichdemmer-ctrl/parkingsimulator (data/cities/). Regenerate with scripts/export_europe.py.

Scope: every city where Q-Park operates, with Q-Park plus the real competing operators found there.
Pricing is taken from each operator's own site or live pricing API. A blank means the operator
does not publish a usable value for that garage; nothing is estimated.

Columns: country, city, id (unique within a city only), name, operator, lat, lon, capacity (spaces),
hourly_rate (first-hour or flat hourly rate, in `currency`), daily_cap (24h price, in `currency`),
has_ev (True when charging was confirmed; blank is unconfirmed), address, source_url, currency.

Caveats: Indigo, Effia and some others publish no capacity, so capacity is blank for them.
Free-first-hour tariffs are recorded as 0.00 or left blank depending on the structure; see the
per-country _progress.csv notes for per-city detail. Competitor coverage is a full list for
small cities but a sample for the largest (e.g. Paris Indigo, Copenhagen APCOA).
"""
open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8").write(readme)
print(len(entries), "cities,", len(out), "rows")
print(out.groupby("country").agg(cities=("city", "nunique"), garages=("id", "count")))
