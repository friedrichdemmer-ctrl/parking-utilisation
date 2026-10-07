"""Try to fix a source that has gone quiet, and only alert on what is left.

alerts.py pushed a phone alert the moment half a source's garages went silent,
whether or not anything could be done about it -- so six alerts on 2026-10-07
all turned out to be operators' own outages, while a seventh problem (Mannheim
losing half its garages when its Designa half froze) had a working fallback
nobody ran. This runs before the alert and does the two repairs that are safe:

1. Re-run the source's own adapter now. The runner backs off after an error --
   doubling to as much as six hours -- so a source that came back can stay
   silent long after it recovered. Running it immediately settles that.

2. Run a fallback adapter: a second upstream that writes the SAME place_ids,
   hand-mapped and verified (FALLBACKS below). Mannheim's garages are also
   published by MobiData BW, whose feed was live throughout the operator's
   outage.

Nothing else is attempted. The watchdog never guesses a name match, never
copies a reading from one garage to another and never writes a value the
source did not give: an operator's outage must look like an outage.

Each attempt is recorded in scraper_runs as adapter "watchdog", kind
<source_id>, so the history of what was tried survives in the database.
"""

from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime, timezone

from scrapers.adapters.mobidata_bw_existing import (
    KarlsruheMobidataBwOccupancyAdapter,
    MannheimMobidataBwOccupancyAdapter,
    UlmMobidataBwOccupancyAdapter,
)

# source_id -> adapters that write the same place_ids from another upstream.
# Only hand-verified 1:1 maps belong here (see mobidata_bw_existing.py, whose
# name maps were built and checked by hand). These three are not in
# scrapers/registry.py: the operators' own feeds replaced them on 2026-10-05,
# and they are kept here as the stand-in for when one of those feeds stops.
FALLBACKS: dict[str, tuple] = {
    "parken-mannheim": (MannheimMobidataBwOccupancyAdapter,),
    "karlsruhe-parken": (KarlsruheMobidataBwOccupancyAdapter,),
    "parken-in-ulm": (UlmMobidataBwOccupancyAdapter,),
}

# how we describe each outcome in the alert and the digest
LABELS = {
    "recovered": "started reporting again on its own",
    "retry": "came back when we re-ran it",
    "fallback": "repaired from a second source",
    "source_frozen": "reachable, but its own timestamps have not moved -- the operator's outage",
    "source_empty": "reachable, but it is publishing no counts",
    "source_unreachable": "we cannot reach it",
    "adapter_error": "our reader for it is failing",
    "no_adapter": "no live adapter -- it arrives through the archive",
}
RESOLVED = ("recovered", "retry", "fallback")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run(conn: sqlite3.Connection, adapter) -> tuple[int, str | None, int]:
    """Fetch and store one adapter's occupancy now. Returns
    (rows written, error or None, rows the source offered)."""
    from scrapers import storage
    from scrapers.runner import _make_fetcher
    from scrapers.validate import filter_valid

    try:
        known = storage.known_garages_for_source(conn, adapter.name)
        caps = storage.known_capacities_for_source(conn, adapter.name)
        records = adapter.fetch_occupancy(_make_fetcher(adapter), known)
        valid, _rejected = filter_valid(records, caps)
        return storage.write_occupancy(conn, valid), None, len(records)
    except Exception as exc:                                  # an adapter must never stop the sweep
        return 0, f"{exc}", 0


def _classify(error: str | None, offered: int) -> str:
    if error:
        lowered = error.lower()
        network = ("http error", "timed out", "timeout", "connection", "ssl", "urlopen", "name or service")
        return "source_unreachable" if any(w in lowered for w in network) else "adapter_error"
    # The source answered and the adapter understood it, but nothing was stored.
    # write_occupancy skips a reading it already holds, so a source re-serving
    # its last values writes nothing: that is the frozen case, not an empty one.
    return "source_frozen" if offered else "source_empty"


def silent_garages(conn: sqlite3.Connection, source_id: str) -> int:
    """How many of a source's garages have not reported within its threshold."""
    import alerts
    from freshness import silent_after

    limit = _now() - silent_after(source_id)
    rows = conn.execute(
        "SELECT last_observed_ts FROM lots_meta WHERE source_id = ? AND last_observed_ts IS NOT NULL "
        "AND place_id NOT IN (SELECT place_id FROM frozen_places)", (source_id,)).fetchall()
    recent = alerts.ACTIVE_DAYS
    cutoff = _now() - __import__("datetime").timedelta(days=recent)
    seen = [alerts._parse(t) for (t,) in rows if t]
    return sum(1 for t in seen if t < limit and t >= cutoff)


def _still_down(conn: sqlite3.Connection, source_id: str) -> bool:
    """Whether the source still counts as down after what we just wrote. A feed
    can be half alive -- Mannheim's Scheidt+Bachmann garages kept reporting
    while its Designa ones froze -- so "we wrote something" is not the test."""
    import alerts

    return source_id in alerts.down_sources(conn)


def repair(conn: sqlite3.Connection, source_id: str) -> dict:
    """One source: re-run it, then try its fallbacks for whatever is still
    silent. Returns {"outcome", "detail", "resolved", "written"}."""
    from scrapers import storage
    from scrapers.registry import ADAPTERS

    adapter = next((a for a in ADAPTERS if a.name == source_id), None)
    if adapter is None:
        return {"outcome": "no_adapter", "detail": "", "resolved": False, "written": 0}

    written, error, offered = _run(conn, adapter)
    if written and not _still_down(conn, source_id):
        out = {"outcome": "retry", "detail": f"{written} readings", "resolved": True, "written": written}
    else:
        outcome = _classify(error, offered) if not written else "source_frozen"
        detail = (error or "")[:200]
        if written:
            detail = f"{written} readings came in, but most of its garages are still silent"
        out = {"outcome": outcome, "detail": detail, "resolved": False, "written": written}
        for cls in FALLBACKS.get(source_id, ()):
            fb = cls()
            fb_written, fb_error, _ = _run(conn, fb)
            if fb_written and not (_still_down(conn, source_id) or silent_garages(conn, source_id)):
                out = {"outcome": "fallback", "resolved": True, "written": written + fb_written,
                       "detail": f"{fb_written} readings from {fb.name} while {source_id} is down ({LABELS[outcome]})"}
                break
            out["detail"] = f"{detail} | fallback {fb.name}: " + (
                f"wrote {fb_written} but the source is still down" if fb_written
                else (fb_error or "nothing to write")[:120])
    try:
        storage.record_run(conn, "watchdog", source_id, "success" if out["resolved"] else "error",
                           records_written=out["written"], error_message=None if out["resolved"] else
                           f"{out['outcome']}: {out['detail']}"[:500])
    except Exception:                                          # recording must not sink the repair
        traceback.print_exc()
    return out


def sweep(conn: sqlite3.Connection, source_ids) -> dict[str, dict]:
    """Try to repair each source. Returns {source_id: result}; callers alert
    only on those whose "resolved" is False."""
    results = {}
    for source_id in sorted(source_ids):
        results[source_id] = repair(conn, source_id)
        state = "fixed" if results[source_id]["resolved"] else "still down"
        print(f"[watchdog] {source_id}: {results[source_id]['outcome']} -- {state}")
    return results


CHECK_INTERVAL_SECONDS = 3600


def run_if_due(conn: sqlite3.Connection) -> None:
    """Hourly: try to repair every source that is currently down, not only the
    ones that went down since the last check -- a fallback is most useful for
    an outage that has been running for a day. Logged in scraper_runs as
    adapter "watchdog", kind "sweep". Runs whether or not alerts are
    configured: repairing does not depend on anyone being told."""
    import traceback

    import alerts
    from scrapers import storage
    from scrapers.runner import _is_due, _last_success_at

    if not _is_due(_last_success_at(conn, "watchdog", "sweep"), CHECK_INTERVAL_SECONDS):
        return
    try:
        # Also sweep a source that has a fallback and some silent garages even
        # when it is not "down" as a whole: Mannheim's live half keeps it above
        # the down threshold while its frozen half would otherwise only be
        # refreshed each time it dipped below, once every six hours.
        down = set(alerts.down_sources(conn))
        down |= {s for s in FALLBACKS if silent_garages(conn, s)}
        results = sweep(conn, sorted(down)) if down else {}
        fixed = [s for s, r in results.items() if r["resolved"]]
        storage.record_run(conn, "watchdog", "sweep", "success", records_written=len(fixed))
        if fixed:
            print(f"[watchdog] repaired {', '.join(fixed)}")
    except Exception as exc:
        storage.record_run(conn, "watchdog", "sweep", "error", error_message=f"{exc}\n{traceback.format_exc()}")
        print(f"[watchdog] sweep FAILED: {exc}")


def line(source_id: str, result: dict) -> str:
    label = LABELS.get(result["outcome"], result["outcome"])
    detail = f" ({result['detail']})" if result.get("detail") else ""
    return f"{source_id}: {label}{detail}"


if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    import alerts

    db = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db"))
    c = sqlite3.connect(db)
    c.execute("PRAGMA busy_timeout=30000")
    targets = sys.argv[1:] or sorted(alerts.down_sources(c))
    if not targets:
        print("[watchdog] nothing is down")
    for sid, res in sweep(c, targets).items():
        print(" ", line(sid, res))
    c.close()
