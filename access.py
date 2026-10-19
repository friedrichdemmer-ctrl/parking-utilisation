"""Password gate for the analysis sections of the site.

Explore, Local maps, Compare and Reports are behind one shared access password. The page is only half
of it: every API those sections call is gated too (PROTECTED below), because a locked page over an open
API would protect nothing. Overview, the live map's data (/api/now, /api/totals), the status pages and
the legal pages stay public.

- The password is the Fly secret SITE_PASSWORD, set by the site owner. If it is not set the protected
  parts answer 503 rather than opening: failing open would publish the data by accident.
- A correct password sets one cookie, tpa_access: "<expiry>.<HMAC-SHA256 of the expiry>", keyed from the
  password, so changing SITE_PASSWORD signs everyone out. HttpOnly, SameSite=Lax, Secure on https. It
  lasts 30 days and is deleted on sign-out. The privacy page says so (legal_pages.py).
- Wrong passwords are limited per IP address: MAX_FAILURES in FAIL_WINDOW seconds, held in memory only
  and forgotten after the window (the privacy notice promises IP addresses are kept for about six
  minutes at most).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from flask import Blueprint, jsonify, redirect, request

COOKIE = "tpa_access"
LIFETIME = 30 * 24 * 3600
FAIL_WINDOW = 5 * 60
MAX_FAILURES = 8
FAIL_DELAY = 0.6                       # seconds, so guessing is slow even before the limit

# path prefixes (end in "/") or exact paths that need the password
PROTECTED_PREFIXES = ("/api/browse/", "/api/city/", "/api/garage/", "/api/local/")
PROTECTED_EXACT = frozenset({
    "/api/briefing", "/api/heatmap", "/api/search", "/api/compare", "/api/garages", "/api/query",
    "/api/cities", "/api/operators", "/report", "/trends", "/yield",
})
PAGES = frozenset({"/report", "/trends", "/yield"})     # HTML pages: send to the site's sign-in, not a 401

bp = Blueprint("access", __name__)
_fails: dict[str, list[float]] = {}


def configured() -> bool:
    return bool(os.environ.get("SITE_PASSWORD"))


def _key() -> bytes:
    return hashlib.sha256(("tpa-access|" + os.environ.get("SITE_PASSWORD", "")).encode("utf-8")).digest()


def make_token(now: float | None = None) -> str:
    expiry = str(int((time.time() if now is None else now) + LIFETIME))
    return f"{expiry}.{hmac.new(_key(), expiry.encode(), hashlib.sha256).hexdigest()}"


def valid_token(token: str | None, now: float | None = None) -> bool:
    if not token or not configured() or "." not in token:
        return False
    expiry, _, sig = token.partition(".")
    if not expiry.isdigit() or int(expiry) < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sig, hmac.new(_key(), expiry.encode(), hashlib.sha256).hexdigest())


def check_password(candidate: str) -> bool:
    expected = os.environ.get("SITE_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or path.startswith(PROTECTED_PREFIXES)


def unlocked() -> bool:
    return valid_token(request.cookies.get(COOKIE))


def _ip() -> str:
    return request.headers.get("Fly-Client-IP") or request.remote_addr or "?"


def _recent_failures(ip: str, now: float) -> list[float]:
    hits = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    if hits:
        _fails[ip] = hits
    else:
        _fails.pop(ip, None)
    return hits


def _secure() -> bool:
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "") == "https"


@bp.route("/api/access")
def api_access():
    return jsonify({"configured": configured(), "unlocked": unlocked()})


@bp.route("/api/login", methods=["POST"])
def api_login():
    if not configured():
        return jsonify({"error": "Access has not been set up yet."}), 503
    now = time.time()
    ip = _ip()
    if len(_recent_failures(ip, now)) >= MAX_FAILURES:
        return jsonify({"error": "Too many wrong passwords. Wait a few minutes and try again."}), 429
    body = request.get_json(silent=True) or {}
    candidate = body.get("password") if isinstance(body.get("password"), str) else ""
    if not check_password(candidate):
        _fails.setdefault(ip, []).append(now)
        time.sleep(FAIL_DELAY)
        return jsonify({"error": "That password is not right."}), 401
    _fails.pop(ip, None)
    resp = jsonify({"unlocked": True})
    resp.set_cookie(COOKIE, make_token(), max_age=LIFETIME, httponly=True, samesite="Lax", secure=_secure(), path="/")
    return resp


@bp.route("/api/logout", methods=["POST"])
def api_logout():
    resp = jsonify({"unlocked": False})
    resp.delete_cookie(COOKIE, path="/")
    return resp


def require_access():
    """before_request: stop unsigned requests to the protected paths."""
    path = request.path
    if not is_protected(path) or unlocked():
        return None
    if not configured():
        return jsonify({"error": "This section is not available yet.", "login": False}), 503
    if path in PAGES:
        return redirect("/#reports", code=302)
    return jsonify({"error": "Sign in to use this part of the site.", "login": True}), 401


def keep_private(response):
    """after_request: what only signed-in visitors may see is never stored by a shared cache."""
    if is_protected(request.path):
        response.headers["Cache-Control"] = "private, no-cache"
    return response


def install(app) -> None:
    app.register_blueprint(bp)
    app.before_request(require_access)
    app.after_request(keep_private)
