"""Analysis requests sent through the site's "Ask us" form.

Stored in their own small SQLite file next to the parking database (requests.db on the /data
volume), never in parking.db. Each request keeps what the visitor typed plus a salted hash of
their IP address (for rate limiting and abuse only). Requests older than RETENTION_DAYS are
deleted whenever a new one arrives; the form tells visitors so.

A new request sends a phone push through the existing ntfy alerts (alerts.send) with only its
number, type and place -- never the email address or the question, because ntfy is a third party.

Read them on the server:
    flyctl ssh console -a parking-utilisation -C "python3 /app/requests_store.py list"
    flyctl ssh console -a parking-utilisation -C "python3 /app/requests_store.py show 3"
    flyctl ssh console -a parking-utilisation -C "python3 /app/requests_store.py done 3"
or at /admin/requests?token=... once the ADMIN_TOKEN secret is set.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db")).parent / "requests.db"
RETENTION_DAYS = 365
KINDS = {
    "city": "A city briefing",
    "site": "A garage or site assessment",
    "benchmark": "Operator or price benchmarking",
    "data": "A question about the data",
    "other": "Something else",
}
LIMITS = {"place": 120, "message": 4000, "name": 120, "organisation": 160, "email": 200}
MIN_MESSAGE = 15
MIN_FILL_MS = 3000            # a person takes longer than this to fill the form
PER_IP_PER_HOUR = 5
PER_DAY = 100
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

SCHEMA = """CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received TEXT NOT NULL,
    kind TEXT NOT NULL,
    place TEXT,
    message TEXT NOT NULL,
    name TEXT,
    organisation TEXT,
    email TEXT NOT NULL,
    ip_hash TEXT,
    status TEXT NOT NULL DEFAULT 'new'
)"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(SCHEMA)
    return conn


def _ip_hash(ip: str) -> str:
    salt = os.environ.get("REQUEST_SALT") or os.environ.get("NTFY_TOPIC") or "theparkinganalysts"
    return hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:16]


def validate(data: dict) -> tuple[dict | None, str | None]:
    """Clean the submitted fields; (fields, None) or (None, a message for the visitor)."""
    if (data.get("website") or "").strip():                       # honeypot, hidden from people
        return None, "spam"
    try:
        if int(data.get("elapsed_ms") or 0) < MIN_FILL_MS:
            return None, "spam"
    except (TypeError, ValueError):
        return None, "spam"
    f = {k: " ".join(str(data.get(k) or "").split()) if k != "message" else str(data.get(k) or "").strip()
         for k in ("kind", "place", "message", "name", "organisation", "email")}
    if f["kind"] not in KINDS:
        return None, "Choose what kind of analysis you are asking for."
    if len(f["message"]) < MIN_MESSAGE:
        return None, "Tell us a little more about what you need (a sentence or two)."
    if not EMAIL.match(f["email"]):
        return None, "Enter an email address we can reply to."
    if not data.get("consent"):
        return None, "Tick the box so we may keep your details to answer you."
    for k, n in LIMITS.items():
        if len(f[k]) > n:
            return None, f"The {k} field is too long (at most {n} characters)."
    return f, None


def add(fields: dict, ip: str) -> tuple[int | None, str | None]:
    """Store a request; (id, None) or (None, a message for the visitor) when over a limit."""
    now = datetime.now(timezone.utc)
    h = _ip_hash(ip)
    conn = _db()
    try:
        conn.execute("DELETE FROM requests WHERE received < ?", ((now - timedelta(days=RETENTION_DAYS)).isoformat(),))
        hour = conn.execute("SELECT COUNT(*) FROM requests WHERE ip_hash = ? AND received >= ?",
                            (h, (now - timedelta(hours=1)).isoformat())).fetchone()[0]
        day = conn.execute("SELECT COUNT(*) FROM requests WHERE received >= ?", ((now - timedelta(days=1)).isoformat(),)).fetchone()[0]
        if hour >= PER_IP_PER_HOUR or day >= PER_DAY:
            return None, "We have received several requests from you in a short time. Please try again later."
        cur = conn.execute("INSERT INTO requests (received, kind, place, message, name, organisation, email, ip_hash) VALUES (?,?,?,?,?,?,?,?)",
                           (now.isoformat(timespec="seconds"), fields["kind"], fields["place"] or None, fields["message"],
                            fields["name"] or None, fields["organisation"] or None, fields["email"], h))
        conn.commit()
        rid = cur.lastrowid
    finally:
        conn.close()
    threading.Thread(target=_notify, args=(rid, fields["kind"], fields["place"]), daemon=True).start()
    return rid, None


def _notify(rid: int, kind: str, place: str) -> None:
    try:
        import alerts
        alerts.send(f"New analysis request #{rid}", f"{KINDS[kind]}{' · ' + place if place else ''}", ["incoming_envelope"], priority=3)
    except Exception as exc:            # a failed push must never lose the request
        print(f"[requests] push failed for #{rid}: {exc}")


def all_requests() -> list[dict]:
    conn = _db()
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT id, received, kind, place, message, name, organisation, email, status FROM requests ORDER BY id DESC")]
    conn.close()
    return rows


def set_status(rid: int, status: str) -> None:
    conn = _db()
    conn.execute("UPDATE requests SET status = ? WHERE id = ?", (status, rid))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for r in all_requests():
            print(f"#{r['id']:<4} {r['received'][:16]}  {r['status']:<5} {KINDS.get(r['kind'], r['kind'])[:30]:<30} {r['place'] or '':<20} {r['email']}")
    elif cmd == "show":
        r = next((r for r in all_requests() if r["id"] == int(sys.argv[2])), None)
        print("\n".join(f"{k}: {v}" for k, v in r.items()) if r else "not found")
    elif cmd in ("done", "new"):
        set_status(int(sys.argv[2]), cmd)
        print(f"#{sys.argv[2]} marked {cmd}")
