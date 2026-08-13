"""Runs due adapters: checks each adapter's own cadence against its last
recorded run, fetches, validates, writes, and records health -- one adapter's
failure never stops the others (the failure mode that silently killed the
original 2021 scraper wholesale, since it was one monolithic process).
"""

from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime, timezone

from scrapers import storage
from scrapers.base import SourceAdapter
from scrapers.fetchers.http_fetcher import HttpFetcher
from scrapers.validate import filter_valid, validate_capacity


def _last_run_at(conn: sqlite3.Connection, adapter: str, kind: str) -> datetime | None:
    row = conn.execute(
        "SELECT run_at FROM scraper_runs WHERE adapter=? AND kind=? ORDER BY run_at DESC LIMIT 1",
        (adapter, kind),
    ).fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def _is_due(last_run: datetime | None, interval_seconds: int) -> bool:
    if last_run is None:
        return True
    return (datetime.now(timezone.utc) - last_run).total_seconds() >= interval_seconds


def _make_fetcher(adapter: SourceAdapter):
    if adapter.fetcher_type == "http":
        return HttpFetcher()
    raise NotImplementedError(f"fetcher_type={adapter.fetcher_type!r} not implemented yet")


def run_capacity(conn: sqlite3.Connection, adapter: SourceAdapter) -> None:
    fetcher = _make_fetcher(adapter)
    try:
        records = adapter.fetch_capacity(fetcher)
        valid = [r for r in records if validate_capacity(r) is None]
        rejected = len(records) - len(valid)
        n = storage.write_capacity(conn, valid)
        storage.record_run(conn, adapter.name, "capacity", "success", records_written=n, records_rejected=rejected)
        print(f"[{adapter.name}] capacity: {n} written, {rejected} rejected")
    except Exception as exc:
        storage.record_run(conn, adapter.name, "capacity", "error", error_message=f"{exc}\n{traceback.format_exc()}")
        print(f"[{adapter.name}] capacity FAILED: {exc}")


def run_occupancy(conn: sqlite3.Connection, adapter: SourceAdapter) -> None:
    fetcher = _make_fetcher(adapter)
    try:
        known_garages = storage.known_garages_for_source(conn, adapter.name)
        known_capacities = storage.known_capacities_for_source(conn, adapter.name)
        records = adapter.fetch_occupancy(fetcher, known_garages)
        valid, rejected = filter_valid(records, known_capacities)
        n = storage.write_occupancy(conn, valid)
        storage.record_run(conn, adapter.name, "occupancy", "success", records_written=n, records_rejected=len(rejected))
        print(f"[{adapter.name}] occupancy: {n} written, {len(rejected)} rejected")
        for rec, reason in rejected[:5]:
            print(f"  rejected {rec.place_id}: {reason}")
    except Exception as exc:
        storage.record_run(conn, adapter.name, "occupancy", "error", error_message=f"{exc}\n{traceback.format_exc()}")
        print(f"[{adapter.name}] occupancy FAILED: {exc}")


def run_due_adapters(conn: sqlite3.Connection, adapters: list[SourceAdapter]) -> None:
    storage.ensure_schema(conn)
    for adapter in adapters:
        if _is_due(_last_run_at(conn, adapter.name, "capacity"), adapter.capacity_interval_seconds):
            run_capacity(conn, adapter)
        if _is_due(_last_run_at(conn, adapter.name, "occupancy"), adapter.occupancy_interval_seconds):
            run_occupancy(conn, adapter)
