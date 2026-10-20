"""Who may sign in, and which cities a demonstrator may see.

Authentication is Kinde's (access.py); the roles live here, in a small SQLite file of their own on the Fly volume
(ACCOUNTS_DB_PATH, default next to parking.db). Kinde says who someone is, this table says what they may do, so a
person can create a Kinde login but sees nothing until the administrator has invited their email address.

Roles:
  admin          everything, plus the Users and Cities pages. The address in ADMIN_EMAIL (default
                 friedrich.demmer@gmail.com) is always an administrator, whatever the table says.
  full           everything except the admin pages.
  demonstrator   Explore, Local maps, Compare and the city briefings for the cities on the allowed list only;
                 the reports; no raw legacy endpoints.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("admin", "full", "demonstrator")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "friedrich.demmer@gmail.com").strip().lower()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The allowed list a demonstrator starts with: the largest German cities that have data (13 of the 14 largest by
# population; Essen is not in our data). The administrator edits it on the Cities page.
DEFAULT_CITIES = [("Germany", c) for c in (
    "Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf",
    "Leipzig", "Dortmund", "Bremen", "Dresden", "Hannover", "Nürnberg")]

_lock = threading.Lock()


def _path() -> Path:
    if os.environ.get("ACCOUNTS_DB_PATH"):
        return Path(os.environ["ACCOUNTS_DB_PATH"])
    base = Path(os.environ.get("PARKING_DB_PATH", Path(__file__).parent / "data" / "parking.db")).parent
    return base / "accounts.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY, role TEXT NOT NULL, name TEXT, invited_by TEXT, invited_at TEXT,
            last_login TEXT, disabled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS allowed_cities (country TEXT NOT NULL, city TEXT NOT NULL, PRIMARY KEY (country, city));
        CREATE TABLE IF NOT EXISTS access_requests (email TEXT PRIMARY KEY, first_at TEXT, last_at TEXT, notified_at TEXT, hits INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    if not c.execute("SELECT 1 FROM meta WHERE k = 'cities_seeded'").fetchone():     # first use: start from the default list once
        c.executemany("INSERT OR IGNORE INTO allowed_cities VALUES (?, ?)", DEFAULT_CITIES)
        c.execute("INSERT INTO meta VALUES ('cities_seeded', ?)", (_now(),))
        c.commit()
    return c


@contextmanager
def _db():
    """One short-lived connection per call, committed and closed afterwards."""
    with _lock:
        c = _conn()
        try:
            yield c
            c.commit()
        finally:
            c.close()


def clean_email(email) -> str | None:
    email = (email or "").strip().lower()
    return email if EMAIL_RE.match(email) and len(email) <= 254 else None


def _row(r) -> dict:
    return {"email": r["email"], "role": r["role"], "name": r["name"], "invited_by": r["invited_by"],
            "invited_at": r["invited_at"], "last_login": r["last_login"], "disabled": bool(r["disabled"])}


def get_user(email: str | None) -> dict | None:
    """The user for an email address, or None. The administrator address is always an active admin."""
    email = clean_email(email)
    if not email:
        return None
    with _db() as c:
        r = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if email == ADMIN_EMAIL:
        u = _row(r) if r else {"email": email, "name": None, "invited_by": None, "invited_at": None, "last_login": None, "disabled": False}
        return {**u, "role": "admin", "disabled": False}
    return _row(r) if r else None


def list_users() -> list[dict]:
    with _db() as c:
        rows = [_row(r) for r in c.execute("SELECT * FROM users ORDER BY role, email")]
    if not any(u["email"] == ADMIN_EMAIL for u in rows):
        rows.insert(0, {"email": ADMIN_EMAIL, "role": "admin", "name": None, "invited_by": None, "invited_at": None, "last_login": None, "disabled": False})
    for u in rows:
        if u["email"] == ADMIN_EMAIL:
            u["role"], u["disabled"], u["protected"] = "admin", False, True
    return rows


def invite(email: str, role: str, invited_by: str, name: str | None = None) -> dict:
    email = clean_email(email)
    if not email:
        raise ValueError("That is not a valid email address.")
    if role not in ROLES:
        raise ValueError("Unknown role.")
    if email == ADMIN_EMAIL:
        raise ValueError("That address is the administrator.")
    with _db() as c:
        c.execute("INSERT INTO users (email, role, name, invited_by, invited_at) VALUES (?, ?, ?, ?, ?) "
                  "ON CONFLICT(email) DO UPDATE SET role = excluded.role, name = COALESCE(excluded.name, name), disabled = 0",
                  (email, role, (name or "").strip() or None, invited_by, _now()))
        c.execute("DELETE FROM access_requests WHERE email = ?", (email,))
    return get_user(email)


def set_role(email: str, role: str) -> dict:
    email = clean_email(email)
    if role not in ROLES:
        raise ValueError("Unknown role.")
    if email == ADMIN_EMAIL:
        raise ValueError("The administrator's role cannot be changed.")
    with _db() as c:
        if not c.execute("UPDATE users SET role = ? WHERE email = ?", (role, email)).rowcount:
            raise ValueError("No such user.")
    return get_user(email)


def set_disabled(email: str, disabled: bool) -> dict:
    email = clean_email(email)
    if email == ADMIN_EMAIL:
        raise ValueError("The administrator cannot be disabled.")
    with _db() as c:
        if not c.execute("UPDATE users SET disabled = ? WHERE email = ?", (1 if disabled else 0, email)).rowcount:
            raise ValueError("No such user.")
    return get_user(email)


def delete_user(email: str) -> None:
    email = clean_email(email)
    if email == ADMIN_EMAIL:
        raise ValueError("The administrator cannot be removed.")
    with _db() as c:
        c.execute("DELETE FROM users WHERE email = ?", (email,))


def touch_login(email: str, name: str | None = None) -> None:
    with _db() as c:
        if email == ADMIN_EMAIL:                # the administrator needs no invitation, so the row is created on first sign-in
            c.execute("INSERT INTO users (email, role, name, last_login) VALUES (?, 'admin', ?, ?) "
                      "ON CONFLICT(email) DO UPDATE SET last_login = excluded.last_login, name = COALESCE(name, excluded.name)",
                      (email, name, _now()))
        else:
            c.execute("UPDATE users SET last_login = ?, name = COALESCE(name, ?) WHERE email = ?", (_now(), name, email))


def allowed_cities() -> list[tuple[str, str]]:
    with _db() as c:
        return [(r["country"], r["city"]) for r in c.execute("SELECT country, city FROM allowed_cities ORDER BY country, city")]


def set_allowed_cities(pairs) -> list[tuple[str, str]]:
    clean = sorted({(str(a).strip(), str(b).strip()) for a, b in pairs if str(a).strip() and str(b).strip()})
    with _db() as c:
        c.execute("DELETE FROM allowed_cities")
        c.executemany("INSERT INTO allowed_cities VALUES (?, ?)", clean)
    return clean


def note_unknown_login(email: str, cooldown_hours: int = 24) -> bool:
    """Record a sign-in by someone who has no account. True when the administrator should be told now
    (at most once per address per cooldown), so repeated attempts do not fill the inbox."""
    email = clean_email(email)
    if not email:
        return False
    now = datetime.now(timezone.utc)
    with _db() as c:
        r = c.execute("SELECT * FROM access_requests WHERE email = ?", (email,)).fetchone()
        if r is None:
            c.execute("INSERT INTO access_requests (email, first_at, last_at, notified_at) VALUES (?, ?, ?, ?)", (email, _now(), _now(), _now()))
            return True
        c.execute("UPDATE access_requests SET last_at = ?, hits = hits + 1 WHERE email = ?", (_now(), email))
        last = datetime.fromisoformat(r["notified_at"]) if r["notified_at"] else None
        if last is None or (now - last).total_seconds() > cooldown_hours * 3600:
            c.execute("UPDATE access_requests SET notified_at = ? WHERE email = ?", (_now(), email))
            return True
    return False


def pending_requests() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT email, first_at, last_at, hits FROM access_requests ORDER BY last_at DESC LIMIT 50")]
