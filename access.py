"""Sign-in and who sees what.

Three kinds of visitor:
  guest   not signed in (or signed up but not yet approved). Sees the Overview and live map, the three reports, every
          city's written briefing, and Explore / Local maps / Compare for the sample cities only.
  member  signed up and approved by the administrator ("full"): everything, for every city.
  admin   a member who also has the Admin page: approvals, members, the sample-city list.

Who someone is comes from Kinde (OpenID Connect, authorization code with PKCE, back-end web app). Anyone may sign up;
a new sign-up is stored as "pending" and sees the guest view until the administrator approves it (accounts.py). The
API handlers in site_api.py and app.py ask scope() / city_ok() before they answer, so a guest cannot reach a
non-sample city through any endpoint.

Modes (mode()):
  kinde     KINDE_DOMAIN, KINDE_CLIENT_ID and KINDE_CLIENT_SECRET are set: the flow above.
  password  only SITE_PASSWORD is set: the shared-password bridge used until Kinde is configured (2026-10-19); whoever
            enters it is a member. Removed once the owner has signed in through Kinde.
  none      neither: everyone is a guest.

The session is one cookie, tpa_session: a signed {email, exp}. The role is read from accounts.py on every request, so
approving, disabling or removing someone takes effect at once. HttpOnly, SameSite=Lax (the return from Kinde is a
top-level GET), Secure on https; 14 days.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape

from flask import Blueprint, Response, g, jsonify, redirect, request

import accounts
import mailer

COOKIE = "tpa_session"
LEGACY_COOKIE = "tpa_access"                # the shared-password cookie (password mode)
OAUTH_COOKIE = "tpa_oauth"                  # state + PKCE verifier while the visitor is at Kinde
SESSION_LIFETIME = 14 * 24 * 3600
LEGACY_LIFETIME = 30 * 24 * 3600
OAUTH_LIFETIME = 10 * 60
FAIL_WINDOW = 5 * 60
MAX_FAILURES = 8
FAIL_DELAY = 0.6

# Answers that differ by visitor (sample cities for a guest, every city for a member): never held by a shared cache.
SCOPED_PREFIXES = ("/api/browse/", "/api/city/", "/api/garage/", "/api/local/", "/api/admin/")
SCOPED_EXACT = frozenset({"/api/briefing", "/api/heatmap", "/api/search", "/api/compare", "/api/garages", "/api/query",
                          "/api/cities", "/api/operators", "/api/access"})
# the older whole-archive endpoints are not city-scoped, so only members may use them
MEMBER_ONLY = frozenset({"/api/garages", "/api/query", "/api/cities", "/api/operators"})
ADMIN_PREFIX = "/api/admin/"

bp = Blueprint("access", __name__)
_fails: dict[str, list[float]] = {}


# ---------------------------------------------------------------- configuration

def site_url() -> str:
    return os.environ.get("SITE_URL", "https://theparkinganalysts.com").rstrip("/")


def kinde_domain() -> str:
    d = os.environ.get("KINDE_DOMAIN", "").strip().rstrip("/")
    return d if not d or d.startswith("http") else "https://" + d


def mode() -> str:
    if kinde_domain() and os.environ.get("KINDE_CLIENT_ID") and os.environ.get("KINDE_CLIENT_SECRET"):
        return "kinde"
    return "password" if os.environ.get("SITE_PASSWORD") else "none"


def configured() -> bool:
    return mode() != "none"


def _key() -> bytes:
    seed = os.environ.get("APP_SECRET") or os.environ.get("KINDE_CLIENT_SECRET") or os.environ.get("SITE_PASSWORD") or ""
    return hashlib.sha256(("tpa-session|" + seed).encode("utf-8")).digest()


# ---------------------------------------------------------------- signed tokens

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict, lifetime: int, now: float | None = None) -> str:
    body = _b64(json.dumps({**payload, "exp": int((time.time() if now is None else now) + lifetime)}, separators=(",", ":")).encode())
    return f"{body}.{_b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())}"


def unsign(token: str | None, now: float | None = None) -> dict | None:
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) and data.get("exp", 0) >= (time.time() if now is None else now) else None


# --- the shared-password bridge (password mode): "<expiry>.<hmac of the expiry>", as before

def make_token(now: float | None = None) -> str:
    expiry = str(int((time.time() if now is None else now) + LEGACY_LIFETIME))
    return f"{expiry}.{hmac.new(_key(), expiry.encode(), hashlib.sha256).hexdigest()}"


def valid_token(token: str | None, now: float | None = None) -> bool:
    if not token or mode() != "password" or "." not in token:
        return False
    expiry, _, sig = token.partition(".")
    if not expiry.isdigit() or int(expiry) < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sig, hmac.new(_key(), expiry.encode(), hashlib.sha256).hexdigest())


def check_password(candidate: str) -> bool:
    expected = os.environ.get("SITE_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


# ---------------------------------------------------------------- the current user and what they may see

def current_user() -> dict | None:
    """The signed-in, enabled account for this request (any role, "pending" included), or None. Read once per request."""
    if hasattr(g, "_tpa_user"):
        return g._tpa_user
    user = None
    if mode() == "kinde":
        s = unsign(request.cookies.get(COOKIE))
        u = accounts.get_user(s.get("email")) if s else None
        user = u if u and not u["disabled"] else None
    elif mode() == "password" and valid_token(request.cookies.get(LEGACY_COOKIE)):
        user = {"email": None, "name": None, "role": "full", "disabled": False}
    g._tpa_user = user
    return user


def role() -> str:
    """admin, full (a member), pending (signed up, not yet approved) or guest (no account)."""
    u = current_user()
    return u["role"] if u else "guest"


def is_member() -> bool:
    return role() in ("admin", "full")


_scope_cache: dict = {"t": 0.0, "v": frozenset()}


def _sample_set() -> frozenset:
    if time.time() - _scope_cache["t"] > 20:
        _scope_cache.update(t=time.time(), v=frozenset(accounts.allowed_cities()))
    return _scope_cache["v"]


def clear_scope_cache() -> None:
    _scope_cache["t"] = 0.0


def scope() -> frozenset | None:
    """None when this visitor may see every city (a member), else the sample cities as a set of (country, city)."""
    return None if is_member() else _sample_set()


def city_ok(country: str | None, city: str | None) -> bool:
    s = scope()
    if s is None:
        return True
    if not city:
        return False
    if country:
        return (country, city) in s
    return any(c == city for _, c in s)        # an older link without a country: only if some sample city has that name


def forbidden():
    return jsonify({"error": "That city is for members. Sign up for full access.", "scope": True}), 403


# ---------------------------------------------------------------- Kinde (OpenID Connect, authorization code + PKCE)

_discovery: dict = {"t": 0.0, "v": None}


def _http(method: str, url: str, data: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    """JSON over HTTPS (replaceable in tests). Returns (status, parsed body or {})."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={"Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {}


def endpoints() -> dict:
    """Kinde's endpoints from its OpenID discovery document (cached an hour), with the documented paths as fallback."""
    if _discovery["v"] and time.time() - _discovery["t"] < 3600:
        return _discovery["v"]
    d = kinde_domain()
    found = {}
    try:
        status, doc = _http("GET", d + "/.well-known/openid-configuration")
        if status == 200:
            found = doc
    except Exception:
        pass
    ep = {
        "authorize": found.get("authorization_endpoint") or d + "/oauth2/auth",
        "token": found.get("token_endpoint") or d + "/oauth2/token",
        "userinfo": found.get("userinfo_endpoint") or d + "/oauth2/v2/user_profile",
        "logout": found.get("end_session_endpoint") or d + "/logout",
    }
    _discovery.update(t=time.time(), v=ep)
    return ep


def _secure() -> bool:
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "") == "https" or site_url().startswith("https")


def _set_cookie(resp, name: str, value: str, max_age: int) -> None:
    resp.set_cookie(name, value, max_age=max_age, httponly=True, samesite="Lax", secure=_secure(), path="/")


def _safe_next(n: str | None) -> str:
    """Where to land after signing in: one of the site's views, never anything else."""
    n = (n or "").lstrip("#").split("/")[0]
    return n if n in ("explore", "local", "compare", "reports", "admin") else "explore"


@bp.route("/signup")
def signup():
    return login(create=True)


@bp.route("/login")
def login(create: bool = False):
    if mode() != "kinde":
        return redirect("/#explore")
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    q = urllib.parse.urlencode({
        "client_id": os.environ["KINDE_CLIENT_ID"], "redirect_uri": site_url() + "/callback", "response_type": "code",
        "scope": "openid profile email", "state": state, "code_challenge_method": "S256",
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        **({"prompt": "create"} if create else {}),         # Kinde's sign-up screen rather than its sign-in screen
    })
    resp = redirect(endpoints()["authorize"] + "?" + q, code=302)
    _set_cookie(resp, OAUTH_COOKIE, sign({"s": state, "v": verifier, "n": _safe_next(request.args.get("next"))}, OAUTH_LIFETIME), OAUTH_LIFETIME)
    return resp


def _page(title: str, body_html: str, status: int = 200) -> Response:
    return Response(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:34rem;margin:12vh auto;padding:0 1rem;color:#111720}}'
        f'a{{color:#1d4f9c}}h1{{font-size:1.5rem}}</style></head><body>{body_html}</body></html>', status=status, mimetype="text/html",
        headers={"Cache-Control": "no-store"})


@bp.route("/callback")
def callback():
    oc = unsign(request.cookies.get(OAUTH_COOKIE))
    if request.args.get("error"):
        return _page("Sign-in cancelled", "<h1>Sign-in cancelled</h1><p><a href='/'>Back to the site</a></p>", 400)
    if not oc or not hmac.compare_digest(str(oc.get("s", "")), request.args.get("state", "")) or not request.args.get("code"):
        return _page("Sign-in failed", "<h1>That sign-in did not complete</h1><p>The link expired or was opened in another browser. <a href='/login'>Try again</a>.</p>", 400)
    ep = endpoints()
    status, tok = _http("POST", ep["token"], {
        "grant_type": "authorization_code", "client_id": os.environ["KINDE_CLIENT_ID"], "client_secret": os.environ["KINDE_CLIENT_SECRET"],
        "code": request.args["code"], "code_verifier": oc["v"], "redirect_uri": site_url() + "/callback"})
    if status != 200 or not tok.get("access_token"):
        return _page("Sign-in failed", "<h1>Kinde did not accept that sign-in</h1><p><a href='/login'>Try again</a>.</p>", 502)
    status, info = _http("GET", ep["userinfo"], headers={"Authorization": "Bearer " + tok["access_token"]})
    email = accounts.clean_email(info.get("email") or info.get("preferred_email"))
    if status != 200 or not email or info.get("email_verified") is False:
        return _page("Sign-in failed", "<h1>We could not confirm your email address</h1><p><a href='/login'>Try again</a>.</p>", 400)
    name = " ".join(x for x in (info.get("given_name"), info.get("family_name")) if x) or info.get("name")
    user = accounts.get_user(email)
    if user is not None and user["disabled"]:
        resp = _page("Access removed", "<h1>This account has no access</h1><p>Please contact the site owner if you think this is a mistake. "
                     "<a href='/logout'>Sign out</a>.</p>", 403)
    else:
        if user is None:                         # a first sign-in: a pending account, and the administrator is told
            user, _ = accounts.register(email, name)
            if user["role"] == "pending":
                threading.Thread(target=mailer.new_signup, args=(accounts.ADMIN_EMAIL, f"{name} <{email}>" if name else email), daemon=True).start()
        accounts.touch_login(email, name)
        resp = redirect("/#" + _safe_next(oc.get("n")), code=302)
        _set_cookie(resp, COOKIE, sign({"email": email}, SESSION_LIFETIME), SESSION_LIFETIME)
    resp.delete_cookie(OAUTH_COOKIE, path="/")
    return resp


@bp.route("/logout")
def logout_page():
    """Ends the site session and Kinde's, so the next sign-in asks again (Kinde needs {site}/ in its allowed logout URLs)."""
    target = endpoints()["logout"] + "?" + urllib.parse.urlencode({"redirect": site_url() + "/"}) if mode() == "kinde" else "/"
    resp = redirect(target, code=302)
    resp.delete_cookie(COOKIE, path="/")
    resp.delete_cookie(LEGACY_COOKIE, path="/")
    return resp


# ---------------------------------------------------------------- the access API

def _public_user(u: dict | None) -> dict | None:
    return {"email": u["email"], "name": u.get("name"), "role": u["role"]} if u else None


@bp.route("/api/access")
def api_access():
    u = current_user()
    s = scope()
    return jsonify({"mode": mode(), "configured": configured(), "signed_in": bool(u), "role": role(), "user": _public_user(u),
                    "member": is_member(), "sample_cities": len(s) if s is not None else None})


def _ip() -> str:
    return request.headers.get("Fly-Client-IP") or request.remote_addr or "?"


def _recent_failures(ip: str, now: float) -> list[float]:
    hits = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    if hits:
        _fails[ip] = hits
    else:
        _fails.pop(ip, None)
    return hits


@bp.route("/api/login", methods=["POST"])
def api_login():
    """The shared-password bridge; only in password mode."""
    if mode() != "password":
        return jsonify({"error": "Use the Sign in button."}), 400
    now = time.time()
    ip = _ip()
    if len(_recent_failures(ip, now)) >= MAX_FAILURES:
        return jsonify({"error": "Too many wrong passwords. Wait a few minutes and try again."}), 429
    body = request.get_json(silent=True) or {}
    if not check_password(body.get("password") if isinstance(body.get("password"), str) else ""):
        _fails.setdefault(ip, []).append(now)
        time.sleep(FAIL_DELAY)
        return jsonify({"error": "That password is not right."}), 401
    _fails.pop(ip, None)
    resp = jsonify({"unlocked": True})
    _set_cookie(resp, LEGACY_COOKIE, make_token(), LEGACY_LIFETIME)
    return resp


@bp.route("/api/logout", methods=["POST"])
def api_logout():
    resp = jsonify({"unlocked": False, "logout_url": "/logout" if mode() == "kinde" else None})
    resp.delete_cookie(LEGACY_COOKIE, path="/")
    return resp


# ---------------------------------------------------------------- the administrator's pages

def _admin_only():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify({"error": "Administrator only."}), 403
    if request.method != "GET" and request.headers.get("X-Requested-With") != "tpa":
        return jsonify({"error": "Missing request header."}), 400
    return None


def _json() -> dict:
    return request.get_json(silent=True) or {}


@bp.route("/api/admin/users")
def admin_users():
    if (denied := _admin_only()):
        return denied
    return jsonify({"users": [u for u in accounts.list_users() if u["role"] != "pending"], "pending": accounts.pending_users(),
                    "email_ready": mailer.configured(), "roles": list(accounts.ROLES), "admin": accounts.ADMIN_EMAIL, "mode": mode()})


@bp.route("/api/admin/users", methods=["POST"])
def admin_add():
    """Add (approve in advance) an address as a member or administrator."""
    if (denied := _admin_only()):
        return denied
    b = _json()
    try:
        user = accounts.add_member(b.get("email"), b.get("role", "full"), current_user()["email"] or accounts.ADMIN_EMAIL, b.get("name"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    sent, err = (False, "Email is not set up.")
    if b.get("send_email", True):
        sent, err = mailer.welcome(user["email"], user.get("name"))
    return jsonify({"user": user, "email_sent": sent, "email_error": err})


@bp.route("/api/admin/users/approve", methods=["POST"])
def admin_approve():
    if (denied := _admin_only()):
        return denied
    b = _json()
    try:
        user = accounts.set_role(b.get("email"), "full")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    sent, err = (False, "Email is not set up.")
    if b.get("send_email", True):
        sent, err = mailer.welcome(user["email"], user.get("name"))
    return jsonify({"user": user, "email_sent": sent, "email_error": err})


def _admin_change(fn):
    if (denied := _admin_only()):
        return denied
    try:
        return jsonify({"user": fn(_json())})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/admin/users/role", methods=["POST"])
def admin_role():
    return _admin_change(lambda b: accounts.set_role(b.get("email"), b.get("role")))


@bp.route("/api/admin/users/disable", methods=["POST"])
def admin_disable():
    return _admin_change(lambda b: accounts.set_disabled(b.get("email"), bool(b.get("disabled", True))))


@bp.route("/api/admin/users/delete", methods=["POST"])
def admin_delete():
    if (denied := _admin_only()):
        return denied
    try:
        accounts.delete_user(_json().get("email"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"deleted": True})


@bp.route("/api/admin/cities")
def admin_cities():
    if (denied := _admin_only()):
        return denied
    from site_api import _index          # every city that has a garage with occupancy history, to pick from

    options = {c: sorted(city for city, gs in cs.items() if any(x[3] for x in gs)) for c, cs in _index().items()}
    return jsonify({"allowed": [{"country": a, "city": b} for a, b in accounts.allowed_cities()],
                    "options": {c: v for c, v in options.items() if v}})


@bp.route("/api/admin/cities", methods=["PUT", "POST"])
def admin_set_cities():
    if (denied := _admin_only()):
        return denied
    rows = _json().get("cities")
    if not isinstance(rows, list):
        return jsonify({"error": "Expected a list of cities."}), 400
    pairs = accounts.set_allowed_cities([(r.get("country"), r.get("city")) for r in rows if isinstance(r, dict)])
    clear_scope_cache()
    return jsonify({"allowed": [{"country": a, "city": b} for a, b in pairs]})


# ---------------------------------------------------------------- the guard

def is_scoped(path: str) -> bool:
    return path in SCOPED_EXACT or path.startswith(SCOPED_PREFIXES)


def require_access():
    """before_request: the admin pages are for the administrator and the whole-archive endpoints for members; everything else
    is open and answers according to scope()."""
    path = request.path
    if path.startswith(ADMIN_PREFIX):
        return None if role() == "admin" else (jsonify({"error": "Administrator only.", "login": not current_user()}),
                                               403 if current_user() else 401)
    if path in MEMBER_ONLY and not is_member():
        return jsonify({"error": "This is for members.", "login": not current_user(), "scope": True}), 403 if current_user() else 401
    return None


def keep_private(response):
    """after_request: what depends on who is asking is never stored by a shared cache."""
    if is_scoped(request.path):
        response.headers["Cache-Control"] = "private, no-cache"
        response.headers["Vary"] = "Cookie"
    return response


def install(app) -> None:
    app.register_blueprint(bp)
    app.before_request(require_access)
    app.after_request(keep_private)
