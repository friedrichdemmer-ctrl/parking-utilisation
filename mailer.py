"""The site's own emails, sent through Brevo's transactional API.

Kinde sends its own sign-in emails (verification codes, password resets); this module is for what the site itself
says: an invitation when the administrator adds someone, and a note to the administrator when somebody signs in
who has no account yet.

Secrets (Fly): BREVO_API_KEY, and BREVO_SENDER_EMAIL, an address verified as a sender in Brevo (and ideally on an
authenticated domain: Brevo requires DKIM/SPF for the sending domain, and a free-mail address such as
gmail.com cannot be authenticated, so mail from one will be rejected or land in spam). BREVO_SENDER_NAME is
optional. send() never raises: it returns (ok, error text), so an email problem cannot break an invitation.
"""

from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request

API = "https://api.brevo.com/v3/smtp/email"
SITE = os.environ.get("SITE_URL", "https://theparkinganalysts.com").rstrip("/")


def configured() -> bool:
    return bool(os.environ.get("BREVO_API_KEY") and os.environ.get("BREVO_SENDER_EMAIL"))


def send(to: str, subject: str, text: str, html_body: str | None = None, post=None) -> tuple[bool, str | None]:
    """Send one email. `post` is for tests: post(url, headers, body_bytes) -> (status, response text)."""
    if not configured():
        return False, "Email is not set up (BREVO_API_KEY / BREVO_SENDER_EMAIL)."
    payload = {
        "sender": {"email": os.environ["BREVO_SENDER_EMAIL"], "name": os.environ.get("BREVO_SENDER_NAME", "TheParkingAnalysts")},
        "to": [{"email": to}], "subject": subject, "textContent": text,
        "htmlContent": html_body or "<p>" + html.escape(text).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>",
    }
    headers = {"api-key": os.environ["BREVO_API_KEY"], "Content-Type": "application/json", "Accept": "application/json"}
    body = json.dumps(payload).encode()
    try:
        if post:
            status, text_back = post(API, headers, body)
        else:
            req = urllib.request.Request(API, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                status, text_back = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text_back = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                     # network failure, timeout...
        return False, f"Could not reach Brevo: {e}"
    if 200 <= status < 300:
        return True, None
    try:
        msg = json.loads(text_back).get("message") or text_back
    except ValueError:
        msg = text_back
    return False, f"Brevo answered {status}: {str(msg)[:200]}"


ROLE_TEXT = {
    "full": ("full user", "all of the site: Explore, Local maps, Compare and the Reports, for every city."),
    "demonstrator": ("demonstrator", "the site for a selected set of cities: Explore, Local maps, Compare, the city briefings and the Reports."),
    "admin": ("administrator", "everything, including the user list."),
}


def invitation(to: str, role: str, name: str | None, invited_by: str) -> tuple[bool, str | None]:
    label, what = ROLE_TEXT[role]
    hello = f"Hello {name}," if name else "Hello,"
    text = (f"{hello}\n\n{invited_by} has given you access to TheParkingAnalysts as a {label}. You can use {what}\n\n"
            f"To sign in, go to {SITE} and choose Sign in. Use this email address ({to}). The first time, you will be asked to create a "
            f"login; a code sent to this address confirms it is yours.\n\n"
            f"TheParkingAnalysts measures how full Europe's car parks are, from live city and operator feeds.\n")
    page = (f"<p>{html.escape(hello)}</p><p>{html.escape(invited_by)} has given you access to <b>TheParkingAnalysts</b> as a "
            f"<b>{html.escape(label)}</b>. You can use {html.escape(what)}</p>"
            f'<p><a href="{SITE}" style="display:inline-block;padding:10px 18px;background:#1d4f9c;color:#fff;text-decoration:none;border-radius:4px">Sign in</a></p>'
            f"<p>Use this email address ({html.escape(to)}). The first time, you will be asked to create a login; a code sent to this address confirms it is yours.</p>"
            f"<p style='color:#6e7886'>TheParkingAnalysts measures how full Europe's car parks are, from live city and operator feeds.</p>")
    return send(to, "You now have access to TheParkingAnalysts", text, page)


def access_request(admin: str, who: str) -> tuple[bool, str | None]:
    text = (f"{who} signed in to TheParkingAnalysts but has no account yet.\n\n"
            f"To give access, open {SITE}/#admin, add the address and choose a role. If you do not recognise the address, ignore this message.\n")
    return send(admin, f"Access request: {who}", text)
