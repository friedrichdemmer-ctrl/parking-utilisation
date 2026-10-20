"""Who may sign in, and which cities a guest may see.

Authentication is Kinde's (access.py); the roles live here, in a small SQLite file of their own on the Fly volume
(ACCOUNTS_DB_PATH, default next to parking.db). Kinde says who someone is, this table says what they may do.

Anyone may sign up; nothing changes for them until the administrator approves them:
  guest (no account, or signed up but not yet approved)
                 the Overview, the three reports and every city's written briefing; Explore, Local maps and
                 Compare for the sample cities only (the list on the Admin page).
  full           a member: everything, for every city.
  admin          a member who also has the Admin page. The address in ADMIN_EMAIL (default
                 friedrich.demmer@gmail.com) is always an administrator.
Stored roles: "pending" (signed up, awaiting approval), "full", "admin". A person the administrator turns down is
disabled, not deleted, so signing up again does not bring them back.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("admin", "full")                 # what the administrator may grant; "pending" is what signing up gives
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "friedrich.demmer@gmail.com").strip().lower()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The sample cities a guest starts with: five German cities with good measured data from our own feeds, and none of the
# cities whose data comes through the Mobilithek (Köln, Düsseldorf, Magdeburg, München, Bremen...), which are held back
# for members. The administrator edits the list on the Admin page.
DEFAULT_CITIES = [("Germany", c) for c in ("Frankfurt", "Dortmund", "Dresden", "Nürnberg", "Mannheim")]
SEED_KEY = "sample_cities_v2"

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
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    if not c.execute("SELECT 1 FROM meta WHERE k = ?", (SEED_KEY,)).fetchone():     # first use: start from the default list once
        c.execute("DELETE FROM allowed_cities")                                       # (replaces the earlier demonstrator list)
        c.executemany("INSERT OR IGNORE INTO allowed_cities VALUES (?, ?)", DEFAULT_CITIES)
        c.execute("INSERT INTO meta VALUES (?, ?)", (SEED_KEY, _now()))
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


def register(email: str, name: str | None = None) -> tuple[dict, bool]:
    """A first sign-in: create the account as "pending" (a guest until approved). Returns (user, created)."""
    email = clean_email(email)
    if not email:
        raise ValueError("That is not a valid email address.")
    if email == ADMIN_EMAIL:
        return get_user(email), False
    with _db() as c:
        created = not c.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if created:
            c.execute("INSERT INTO users (email, role, name, invited_at, last_login) VALUES (?, 'pending', ?, ?, ?)",
                      (email, (name or "").strip() or None, _now(), _now()))
    return get_user(email), created


def add_member(email: str, role: str, added_by: str, name: str | None = None) -> dict:
    """The administrator adds (or approves in advance) an address: it has the role as soon as it signs in."""
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
                  (email, role, (name or "").strip() or None, added_by, _now()))
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


def pending_users() -> list[dict]:
    """People who have signed up and are waiting for approval, newest first."""
    with _db() as c:
        return [_row(r) for r in c.execute("SELECT * FROM users WHERE role = 'pending' AND disabled = 0 ORDER BY invited_at DESC")]
