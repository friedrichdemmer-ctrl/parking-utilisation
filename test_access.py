"""End-to-end checks of the account system against the real app, with a stand-in for Kinde.

    pip install flask   # in a throwaway venv; the production image has it
    python3 test_access.py

Builds a small throwaway database (Berlin, Hamburg, Köln, Salzburg, Münster, Torino), runs the real Flask app with
Kinde's token and userinfo calls replaced by a fake that checks the PKCE verifier, and signs people in as the
administrator, a demonstrator and a full user. Nothing here touches the network or the production database.
"""
import base64
import hashlib
import os
import sqlite3
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp())
os.environ.update(PARKING_DB_PATH=str(tmp / "parking.db"), ACCOUNTS_DB_PATH=str(tmp / "accounts.db"),
                  SITE_URL="http://localhost:5099", APP_SECRET="test-secret")
for k in ("KINDE_DOMAIN", "KINDE_CLIENT_ID", "KINDE_CLIENT_SECRET", "SITE_PASSWORD", "BREVO_API_KEY", "BREVO_SENDER_EMAIL"):
    os.environ.pop(k, None)

import import_historical
from scrapers import storage

c = sqlite3.connect(os.environ["PARKING_DB_PATH"])
c.executescript(import_historical.SCHEMA)
storage.ensure_schema(c)
c.execute("create table feed_health (place_id text primary key, source_id text, status text)")
for pid, name, city, cap, src in [("b1", "Berlin Parkhaus", "Berlin", 300, "x-berlin"), ("h1", "Hamburg Garage", "Hamburg", 200, "x-hh"),
                                  ("k1", "Köln Dom", "Köln", 500, "x-koeln"), ("s1", "Salzburg Garage", "Salzburg", 150, "parken-at"),
                                  ("m1", "Münster Garage", "Münster", 100, "x-ms"), ("t1", "Torino Garage", "Torino", 250, "torino-5t")]:
    c.execute("insert into lots_meta (place_id, place_name, city_name, num_all, source_id, last_observed_ts) values (?,?,?,?,?,?)",
              (pid, name, city, cap, src, "2026-10-19T10:00:00+00:00"))
c.commit()
c.close()

import accounts
import access
import app as site
import mailer

app = site.app
sent = []
mailer.send = lambda to, subject, text, html_body=None, post=None: (sent.append((to, subject)) or (True, None))


def check(cond, msg):
    if not cond:
        raise SystemExit("FAIL: " + msg)


# ---- a stand-in for Kinde: authorization codes bound to a PKCE challenge, a token endpoint and a userinfo endpoint
codes, USERS = {}, {"friedrich.demmer@gmail.com": "Friedrich Demmer", "anna@example.com": "Anna Test", "bob@example.com": "Bob Test",
                    "stranger@example.com": "Nobody Known"}


def fake_http(method, url, data=None, headers=None):
    if url.endswith("/.well-known/openid-configuration"):
        return 404, {}
    if url.endswith("/oauth2/token"):
        rec = codes.pop(data.get("code"), None)
        ok = rec and data["client_secret"] == "sekret" and data["redirect_uri"] == "http://localhost:5099/callback" \
            and base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).rstrip(b"=").decode() == rec["challenge"]
        return (200, {"access_token": "tok-" + rec["email"]}) if ok else (400, {"error": "invalid_grant"})
    if url.endswith("/oauth2/v2/user_profile"):
        email = (headers or {}).get("Authorization", "")[len("Bearer tok-"):]
        return (200, {"email": email, "given_name": USERS[email].split()[0], "family_name": USERS[email].split()[1]}) if email in USERS else (401, {})
    return 404, {}


access._http = fake_http


def sign_in(email):
    """Walk the real /login -> authorize -> /callback round trip; returns a client holding the session cookie."""
    cl = app.test_client()
    r = cl.get("/login?next=explore")
    check(r.status_code == 302 and "/oauth2/auth" in r.location, "login redirects to Kinde")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.location).query))
    check(q["code_challenge_method"] == "S256" and q["redirect_uri"] == "http://localhost:5099/callback" and q["client_id"] == "cid", "authorize parameters")
    code = "code-" + email
    codes[code] = {"email": email, "challenge": q["code_challenge"]}
    r = cl.get("/callback?" + urllib.parse.urlencode({"code": code, "state": q["state"]}))
    return cl, r


def api(cl, path, method="GET", json=None, headers=None):
    return cl.open(path, method=method, json=json, headers=headers or {})


# ================= mode none: nothing opens
r = app.test_client().get("/api/browse/countries")
check(r.status_code == 503, "unconfigured mode must fail closed")
check(app.test_client().get("/api/access").get_json()["mode"] == "none", "mode none")

# ================= Kinde mode
os.environ.update(KINDE_DOMAIN="https://example.kinde.com", KINDE_CLIENT_ID="cid", KINDE_CLIENT_SECRET="sekret")
check(access.mode() == "kinde", "kinde mode")
anon = app.test_client()
check(anon.get("/api/now").status_code in (200, 500), "public endpoint untouched")
check(anon.get("/api/browse/countries").status_code == 401, "anonymous is refused")
check(anon.get("/report").status_code == 302, "report page redirects to the sign-in")
check(anon.get("/api/access").get_json()["unlocked"] is False, "anonymous access state")

# a Kinde login without an invitation gets nothing, and the administrator is told once
cl, r = sign_in("stranger@example.com")
check(r.status_code == 403 and b"No access yet" in r.data, "uninvited sign-in is refused")
check(cl.get("/api/browse/countries").status_code == 401, "no session for an uninvited address")
check(any(x["email"] == "stranger@example.com" for x in accounts.pending_requests()), "the request is recorded")
# a tampered state or an unknown code is refused
cl2 = app.test_client(); cl2.get("/login")
check(cl2.get("/callback?code=x&state=wrong").status_code == 400, "wrong state")
check(app.test_client().get("/callback?code=x&state=y").status_code == 400, "callback without the login cookie")

# the administrator needs no invitation
admin, r = sign_in("friedrich.demmer@gmail.com")
check(r.status_code == 302 and r.location.endswith("/#explore"), "admin lands on the requested view")
me = admin.get("/api/access").get_json()
check(me["unlocked"] and me["user"]["role"] == "admin" and me["cities"] is None, "admin sees everything")
check(admin.get("/api/admin/users").status_code == 200, "admin API")
check(admin.post("/api/admin/users", json={"email": "anna@example.com", "role": "demonstrator"}).status_code == 400, "writes need the request header")
H = {"X-Requested-With": "tpa"}
rr = api(admin, "/api/admin/users", "POST", {"email": "Anna@Example.com", "role": "demonstrator", "name": "Anna"}, H).get_json()
check(rr["user"]["role"] == "demonstrator" and rr["email_sent"] and sent[-1][0] == "anna@example.com", "invite sends the email")
api(admin, "/api/admin/users", "POST", {"email": "bob@example.com", "role": "full"}, H)
check(api(admin, "/api/admin/users", "POST", {"email": "nope", "role": "full"}, H).status_code == 400, "bad email refused")
check(api(admin, "/api/admin/users", "POST", {"email": "x@y.de", "role": "king"}, H).status_code == 400, "bad role refused")

# ---- the demonstrator sees only the allowed cities
demo, r = sign_in("anna@example.com")
check(r.status_code == 302, "invited demonstrator signs in")
me = demo.get("/api/access").get_json()
check(me["user"]["role"] == "demonstrator" and me["cities"] == 13, "demonstrator role and city count")
check(demo.get("/api/admin/users").status_code == 403, "demonstrator cannot use the admin API")
countries = demo.get("/api/browse/countries").get_json()
check([c["country"] for c in countries] == ["Germany"], f"only Germany is visible: {countries}")
cities = {c["city"] for c in demo.get("/api/browse/cities?country=Germany").get_json()}
check(cities == {"Berlin", "Hamburg", "Köln"}, f"allowed cities only: {cities}")        # Münster is not on the default list
check(demo.get("/api/browse/cities?country=Austria").status_code == 404, "other countries do not exist for a demonstrator")
check(demo.get("/api/browse/garages?country=Germany&city=Berlin").status_code == 200, "allowed city's garages")
check(demo.get("/api/browse/garages?country=Austria&city=Salzburg").status_code == 404, "other city's garages hidden")
check(demo.get("/api/city/Salzburg?country=Austria").status_code == 403, "city page refused")
check(demo.get("/api/city/Münster?country=Germany").status_code == 403, "an unlisted German city is refused")
check(demo.get("/api/city/Berlin?country=Germany").status_code not in (401, 403), "allowed city page is not refused")
check(demo.get("/api/garage/s1").status_code == 403, "garage in another city refused")
check(demo.get("/api/garage/b1").status_code not in (401, 403), "garage in an allowed city is not refused")
check(demo.get("/api/briefing?country=Austria&city=Salzburg").status_code == 403, "briefing refused")
check(demo.get("/api/briefing?country=Germany&city=Berlin").status_code != 403, "allowed briefing not refused")
check(demo.get("/api/heatmap?place_id=s1").status_code == 403, "heatmap refused")
check(api(demo, "/api/compare", "POST", {"entities": [{"scope_type": "garage", "scope_value": "s1"}]}, H).status_code == 403, "compare refuses a garage outside the list")
check(api(demo, "/api/compare", "POST", {"entities": [{"scope_type": "city", "scope_value": "Salzburg", "country": "Austria"}]}, H).status_code == 403, "compare refuses a city outside the list")
found = demo.get("/api/search?q=a").get_json()
check(all(g["city"] in ("Berlin", "Hamburg", "Köln") for g in found["garages"]) and all(x["country"] == "Germany" for x in found["cities"]), "search is limited too")
check(not any(g["city"] == "Salzburg" for g in demo.get("/api/search?q=Salzburg").get_json()["garages"]), "search hides other cities by name")
check(demo.get("/api/garages").status_code == 403 and demo.get("/api/query").status_code == 403, "the whole-archive endpoints are closed to a demonstrator")
check(demo.get("/report").status_code != 302, "reports are open to a demonstrator")

# ---- a full user sees everything but not the admin pages
full, r = sign_in("bob@example.com")
check({c["country"] for c in full.get("/api/browse/countries").get_json()} == {"Germany", "Austria", "Italy"}, "full user sees every country")
check(full.get("/api/city/Salzburg?country=Austria").status_code != 403, "full user may open any city")
check(full.get("/api/admin/users").status_code == 403, "full user is not an administrator")

# ---- the administrator changes things and the effect is immediate
api(admin, "/api/admin/cities", "PUT", {"cities": [{"country": "Austria", "city": "Salzburg"}]}, H)
check({c["country"] for c in demo.get("/api/browse/countries").get_json()} == {"Austria"}, "city list change applies at once")
check(demo.get("/api/city/Salzburg?country=Austria").status_code != 403 and demo.get("/api/city/Berlin?country=Germany").status_code == 403, "new list enforced")
check(api(admin, "/api/admin/users/role", "POST", {"email": "anna@example.com", "role": "full"}, H).status_code == 200, "role change")
check(demo.get("/api/city/Berlin?country=Germany").status_code != 403, "promoted to full: sees Berlin now")
api(admin, "/api/admin/users/disable", "POST", {"email": "anna@example.com", "disabled": True}, H)
check(demo.get("/api/browse/countries").status_code == 401, "a disabled user is out at once")
check(api(admin, "/api/admin/users/role", "POST", {"email": accounts.ADMIN_EMAIL, "role": "full"}, H).status_code == 400, "the administrator cannot be demoted")
api(admin, "/api/admin/users/delete", "POST", {"email": "bob@example.com"}, H)
check(full.get("/api/browse/countries").status_code == 401, "a removed user is out at once")
check(sign_in("anna@example.com")[1].status_code == 403, "a disabled user cannot sign in again")

# ---- sign-out ends the session and sends the browser on to Kinde's logout
out = admin.post("/api/logout", headers=H).get_json()
check(out["logout_url"] == "/logout", "logout url")
r = admin.get("/logout")
check(r.status_code == 302 and "example.kinde.com/logout" in r.location and "redirect=http%3A%2F%2Flocalhost%3A5099%2F" in r.location, "Kinde logout")
check(admin.get("/api/browse/countries").status_code == 401, "the session cookie is gone")

# ---- a forged or expired session cookie is worthless
forged = app.test_client()
forged.set_cookie("tpa_session", access.sign({"email": "friedrich.demmer@gmail.com"}, -10), domain="localhost")
check(forged.get("/api/browse/countries").status_code == 401, "expired session")
forged.set_cookie("tpa_session", access.sign({"email": "friedrich.demmer@gmail.com"}, 100)[:-3] + "abc", domain="localhost")
check(forged.get("/api/browse/countries").status_code == 401, "forged session")

# ================= the shared-password bridge still works while Kinde is not configured
for k in ("KINDE_DOMAIN", "KINDE_CLIENT_ID", "KINDE_CLIENT_SECRET"):
    os.environ.pop(k)
os.environ["SITE_PASSWORD"] = "pw-123"
pw = app.test_client()
check(pw.get("/api/browse/countries").status_code == 401, "password mode refuses anonymous")
check(pw.post("/api/login", json={"password": "wrong"}).status_code == 401, "wrong password")
check(pw.post("/api/login", json={"password": "pw-123"}).status_code == 200, "right password")
check(pw.get("/api/browse/countries").status_code == 200 and pw.get("/api/access").get_json()["user"]["role"] == "full", "password users are full users")
check(pw.get("/api/admin/users").status_code == 403, "and not administrators")
print("access: all checks passed")
