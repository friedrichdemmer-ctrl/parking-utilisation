#!/usr/bin/env python3
"""Merge researched tariffs (filled_*.csv) into a prices file this project reads.

The research files key on our own place_id, so no coordinate matching is
needed -- but each row still has to be checked: a rate that is absurd for
its city, or a day ticket below the hourly rate, means the researcher read
the wrong page. Rows that fail are written to _rejected.csv with a reason
rather than silently dropped.

Two kinds of row are kept but marked rather than priced: sites that are free
(a free park-and-ride earns nothing) and sites whose fee is conditional on a
transit ticket (a transit authority subsidises them, so the posted fee is not
what the site takes). Both are excluded from revenue modelling.

Usage: python3 garage_prices/merge_filled.py [--write]
Without --write it only reports what it would do.
"""
from __future__ import annotations

import csv, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNPRICED = HERE / "_unpriced_2026-10.csv"
OUT = HERE / "prices_researched_2026-10.csv"
REJECTS = HERE / "_rejected.csv"
# Plausibility bounds per hour, by currency -- wide enough for the real
# extremes, tight enough to catch a day rate read as an hourly one. Central
# Amsterdam sets the ceiling: Waterlooplein is EUR 14.00/h and Rembrandtplein
# EUR 13.00/h in 2026, both verified, so a EUR 12 cap rejected good rows.
BOUNDS = {"EUR": (0.2, 20.0), "CHF": (0.5, 20.0), "GBP": (0.3, 20.0), "DKK": (3.0, 150.0)}

def main() -> None:
    known = {r["place_id"]: r for r in csv.DictReader(open(UNPRICED, encoding="utf-8"))}
    rows, rejects, seen = [], [], set()
    for path in sorted(HERE.glob("filled_*.csv")):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            pid = (r.get("place_id") or "").strip()
            src = path.name
            def bad(why): rejects.append({"file": src, "place_id": pid, "why": why, **r})
            if pid not in known:
                bad("place_id not in the unpriced list"); continue
            if pid in seen:
                bad("duplicate place_id"); continue
            cur = (r.get("currency") or "EUR").strip().upper() or "EUR"
            def num(k):
                v = (r.get(k) or "").strip().replace(",", ".").replace("€", "").replace("£", "")
                try: return float(v)
                except ValueError: return None
            hr, dc = num("hourly_rate"), num("daily_cap")
            if hr is None and dc is None:
                bad("no price"); continue
            note = (r.get("note") or "").strip()
            # free sites are data, not errors: a free park-and-ride earns
            # nothing and must not be modelled as a commercial garage
            free = (hr in (0, None) and dc in (0, None)) or "free" in note.lower()[:40]
            # a transit authority subsidises these, so the posted fee is not
            # what the site takes; they are kept but excluded from revenue
            transit = "transit-conditional" in note.lower() or "includes transit" in note.lower()
            lo, hi = BOUNDS.get(cur, BOUNDS["EUR"])
            if not free and hr is not None and hr > 0 and not (lo <= hr <= hi):
                bad(f"hourly {hr} outside {lo}-{hi} {cur}"); continue
            if not free and dc is not None and hr is not None and hr > 0 and dc < hr:
                bad(f"day ticket {dc} below the hourly rate {hr}"); continue
            if not free and dc is not None and hr is not None and hr > 0 and dc > hr * 24:
                bad(f"day ticket {dc} above 24h at {hr}"); continue
            if not (r.get("source_url") or "").strip().startswith("http"):
                bad("no source url"); continue
            k = known[pid]
            seen.add(pid)
            rows.append({"place_id": pid, "place_name": k["name"], "city_name": k["city"],
                         "our_capacity": k["capacity"], "priced_name": (r.get("listed_name") or "").strip() or k["name"],
                         "priced_city": k["city"], "country": cur.lower(), "operator": (r.get("operator") or "").strip(),
                         "priced_capacity": "", "hourly_rate": hr if hr is not None else "",
                         "daily_cap": dc if dc is not None else "", "dist_m": 0, "name_sim": "",
                         "reporting": "yes", "source_url": r["source_url"].strip(),
                         "currency": cur, "note": note,
                         "free": "yes" if free else "", "transit_conditional": "yes" if transit else ""})
    n_free = sum(1 for r in rows if r["free"]); n_tr = sum(1 for r in rows if r["transit_conditional"])
    print(f"{len(rows)} accepted ({n_free} free, {n_tr} transit-conditional), {len(rejects)} rejected, "
          f"from {len(list(HERE.glob('filled_*.csv')))} files")
    for r in rejects[:15]:
        print(f"  reject {r['place_id'][:46]:46} {r['why']}")
    if "--write" in sys.argv and rows:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        if rejects:
            with open(REJECTS, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rejects[0])); w.writeheader(); w.writerows(rejects)
        print(f"wrote {OUT.name}" + (f" and {REJECTS.name}" if rejects else ""))

if __name__ == "__main__":
    main()
