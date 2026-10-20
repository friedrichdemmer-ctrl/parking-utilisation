"""End-to-end checks of the account system against the real app, with a stand-in for Kinde.

    pip install flask   # in a throwaway venv; the production image has it
    python3 test_access.py

Builds a small throwaway database (Frankfurt and Dortmund are sample cities; Berlin, Köln, Salzburg and Torino are not), runs the real Flask app with
Kinde's token and userinfo calls replaced by a fake that checks the PKCE verifier, and checks the guest, the pending sign-up, the
member and the administrator. Nothing here touches the network or the production database.
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
for pid, name, city, cap, src in [("f1", "Frankfurt Hauptwache", "Frankfurt", 300, "x-ffm"), ("d1", "Dortmund Garage", "Dortmund", 200, "x-do"),
                                  ("b1", "Berlin Parkhaus", "Berlin", 300, "x-berlin"), ("k1", "Köln Dom", "Köln", 500, "x-koeln"),
                                  ("s1", "Salzburg Garage", "Salzburg", 150, "parken-at"), ("t1", "Torino Garage", "Torino", 250, "torino-5t")]:
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
signups = []
mailer.new_signup = lambda admin, who: (signups.append(who) or (True, None))


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


# ================= mode none: everyone is a guest, nothing breaks
g0 = app.test_client()
check(g0.get("/api/access").get_json()["mode"] == "none" and g0.get("/api/access").get_json()["role"] == "guest", "mode none: guest")
check({c["city"] for c in g0.get("/api/browse/cities?country=Germany").get_json()} == {"Frankfurt", "Dortmund"}, "guests see only the sample cities")

# ================= Kinde mode
os.environ.update(KINDE_DOMAIN="https://example.kinde.com", KINDE_CLIENT_ID="cid", KINDE_CLIENT_SECRET="sekret")
check(access.mode() == "kinde", "kinde mode")
guest = app.test_client()
me = guest.get("/api/access").get_json()
check(me["role"] == "guest" and not me["signed_in"] and me["sample_cities"] == 5, f"guest state: {me}")
check(guest.get("/api/now").status_code in (200, 500), "public endpoint untouched")
check(guest.get("/report").status_code != 302 and guest.get("/trends").status_code != 302 and guest.get("/yield").status_code != 302, "the reports are open to guests")
check([c["country"] for c in guest.get("/api/browse/countries").get_json()] == ["Germany"], "a guest sees only the country of the sample cities")
check(guest.get("/api/browse/garages?country=Germany&city=Frankfurt").status_code == 200, "a sample city's garages")
check(guest.get("/api/browse/garages?country=Germany&city=Berlin").status_code == 404, "another city's garages are hidden")
check(guest.get("/api/city/Frankfurt?country=Germany").status_code not in (401, 403), "a sample city's page")
check(guest.get("/api/city/Berlin?country=Germany").status_code == 403, "another city's page is for members")
check(guest.get("/api/city/Salzburg?country=Austria").status_code == 403, "so is a foreign city's")
check(guest.get("/api/garage/b1").status_code == 403 and guest.get("/api/garage/f1").status_code not in (401, 403), "garage pages follow the same rule")
check(guest.get("/api/heatmap?place_id=b1").status_code == 403, "heatmap follows it too")
check(guest.get("/api/briefing?country=Germany&city=Berlin").status_code != 403, "every city's briefing is open to guests")
check(guest.get("/api/briefing?country=Austria&city=Salzburg").status_code != 403, "also a foreign city's")
check(guest.post("/api/compare", json={"entities": [{"scope_type": "garage", "scope_value": "b1"}]}).status_code == 403, "compare refuses a non-sample garage")
check(guest.get("/api/local/cities?country=Germany").status_code in (200, 404) and guest.get("/api/local/map?country=Germany&city=Berlin").status_code == 403, "local maps follow the rule")
found = guest.get("/api/search?q=a").get_json()
check(all(g["city"] in ("Frankfurt", "Dortmund") for g in found["garages"]) and all(x["city"] in ("Frankfurt", "Dortmund") for x in found["cities"]), "search is limited")
check(guest.get("/api/garages").status_code == 401 and guest.get("/api/query").status_code == 401, "the whole-archive endpoints need an account")
check(guest.get("/api/admin/users").status_code == 401, "the admin API needs the administrator")
check("Cookie" in guest.get("/api/browse/countries").headers.get("Vary", ""), "scoped answers vary by cookie")

# ---- anyone may sign up: a new account is pending, and the administrator is told
newbie, r = sign_in("anna@example.com")
check(r.status_code == 302 and r.location.endswith("/#explore"), "a first sign-in is accepted")
me = newbie.get("/api/access").get_json()
check(me["signed_in"] and me["role"] == "pending" and not me["member"], f"pending until approved: {me}")
check(signups and "anna@example.com" in signups[-1], "the administrator is told of the sign-up")
check(newbie.get("/api/city/Berlin?country=Germany").status_code == 403, "a pending sign-up still sees only the guest view")
check(newbie.get("/api/garages").status_code == 403, "and cannot use the member-only endpoints")
check(newbie.get("/api/admin/users").status_code == 403, "nor the admin API")
n_before = len(signups); sign_in("anna@example.com")
check(len(signups) == n_before, "signing in again does not notify again")

# the administrator needs no approval
admin, r = sign_in("friedrich.demmer@gmail.com")
me = admin.get("/api/access").get_json()
check(me["role"] == "admin" and me["member"] and me["sample_cities"] is None, "the administrator sees everything")
H = {"X-Requested-With": "tpa"}
check(admin.post("/api/admin/users/approve", json={"email": "anna@example.com"}).status_code == 400, "writes need the request header")
d = admin.get("/api/admin/users").get_json()
check([p["email"] for p in d["pending"]] == ["anna@example.com"] and all(u["role"] != "pending" for u in d["users"]), "pending list")

# ---- approval gives full access at once
rr = api(admin, "/api/admin/users/approve", "POST", {"email": "anna@example.com"}, H).get_json()
check(rr["user"]["role"] == "full" and rr["email_sent"] and sent[-1][0] == "anna@example.com", "approval emails the member")
check(newbie.get("/api/access").get_json()["member"], "now a member")
check(newbie.get("/api/city/Berlin?country=Germany").status_code not in (401, 403), "a member sees any city")
check({c["country"] for c in newbie.get("/api/browse/countries").get_json()} == {"Germany", "Austria", "Italy"}, "and every country")
check(newbie.get("/api/garages").status_code not in (401, 403), "and the whole-archive endpoints")
check(newbie.get("/api/admin/users").status_code == 403, "but not the admin pages")

# ---- the administrator can add someone in advance, change roles, disable, reject, remove
rr = api(admin, "/api/admin/users", "POST", {"email": "Bob@Example.com", "role": "full", "name": "Bob"}, H).get_json()
check(rr["user"]["role"] == "full" and rr["email_sent"], "add a member in advance")
bob, r = sign_in("bob@example.com")
check(bob.get("/api/access").get_json()["member"] and not signups[-1].startswith("bob"), "an added member is full at once and is not a sign-up")
check(api(admin, "/api/admin/users", "POST", {"email": "nope", "role": "full"}, H).status_code == 400, "bad email refused")
check(api(admin, "/api/admin/users", "POST", {"email": "x@y.de", "role": "pending"}, H).status_code == 400, "only real roles can be granted")
check(api(admin, "/api/admin/users/role", "POST", {"email": accounts.ADMIN_EMAIL, "role": "full"}, H).status_code == 400, "the administrator cannot be demoted")
carla, r = sign_in("stranger@example.com")
check(carla.get("/api/access").get_json()["role"] == "pending", "another sign-up")
api(admin, "/api/admin/users/disable", "POST", {"email": "stranger@example.com", "disabled": True}, H)
check(carla.get("/api/access").get_json()["role"] == "guest", "a rejected sign-up is a guest again at once")
check(sign_in("stranger@example.com")[1].status_code == 403, "and cannot sign in again")
api(admin, "/api/admin/users/disable", "POST", {"email": "anna@example.com", "disabled": True}, H)
check(newbie.get("/api/city/Berlin?country=Germany").status_code == 403, "a disabled member is out at once")
api(admin, "/api/admin/users/delete", "POST", {"email": "bob@example.com"}, H)
check(bob.get("/api/city/Berlin?country=Germany").status_code == 403, "a removed member is out at once")

# ---- the sample list is the administrator's to change, and applies to guests at once
api(admin, "/api/admin/cities", "PUT", {"cities": [{"country": "Austria", "city": "Salzburg"}]}, H)
check({c["country"] for c in guest.get("/api/browse/countries").get_json()} == {"Austria"}, "the sample list change applies at once")
check(guest.get("/api/city/Salzburg?country=Austria").status_code != 403 and guest.get("/api/city/Frankfurt?country=Germany").status_code == 403, "new list enforced")
check(guest.post("/api/admin/cities", json={"cities": []}, headers=H).status_code == 401, "guests cannot change it")

# ---- sign-out ends the session and sends the browser on to Kinde's logout
out = admin.post("/api/logout", headers=H).get_json()
check(out["logout_url"] == "/logout", "logout url")
r = admin.get("/logout")
check(r.status_code == 302 and "example.kinde.com/logout" in r.location and "redirect=http%3A%2F%2Flocalhost%3A5099%2F" in r.location, "Kinde logout")
check(admin.get("/api/access").get_json()["role"] == "guest", "the session cookie is gone")

# ---- the sign-up link asks Kinde for its registration screen
r = app.test_client().get("/signup")
check(r.status_code == 302 and "prompt=create" in r.location, "sign-up uses Kinde's registration screen")

# ---- a forged or expired session cookie is worthless
forged = app.test_client()
forged.set_cookie("tpa_session", access.sign({"email": "friedrich.demmer@gmail.com"}, -10), domain="localhost")
check(forged.get("/api/access").get_json()["role"] == "guest", "expired session")
forged.set_cookie("tpa_session", access.sign({"email": "friedrich.demmer@gmail.com"}, 100)[:-3] + "abc", domain="localhost")
check(forged.get("/api/access").get_json()["role"] == "guest", "forged session")

# ================= the shared-password bridge still works while Kinde is not configured
for k in ("KINDE_DOMAIN", "KINDE_CLIENT_ID", "KINDE_CLIENT_SECRET"):
    os.environ.pop(k)
os.environ["SITE_PASSWORD"] = "pw-123"
accounts.set_allowed_cities([("Germany", "Frankfurt"), ("Germany", "Dortmund")])
access.clear_scope_cache()
pw = app.test_client()
check(pw.get("/api/access").get_json()["mode"] == "password" and pw.get("/api/city/Berlin?country=Germany").status_code == 403, "password mode: guests see the sample cities")
check(pw.post("/api/login", json={"password": "wrong"}).status_code == 401, "wrong password")
check(pw.post("/api/login", json={"password": "pw-123"}).status_code == 200, "right password")
check(pw.get("/api/city/Berlin?country=Germany").status_code not in (401, 403) and pw.get("/api/access").get_json()["role"] == "full", "the password gives a member")
check(pw.get("/api/admin/users").status_code == 403, "and not the admin pages")
print("access: all checks passed")
