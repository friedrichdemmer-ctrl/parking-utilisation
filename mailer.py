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


def welcome(to: str, name: str | None) -> tuple[bool, str | None]:
    """Sent when the administrator approves a sign-up (or adds a member): they now see every city."""
    hello = f"Hello {name}," if name else "Hello,"
    text = (f"{hello}\n\nYour sign-up to TheParkingAnalysts has been approved. You now have full access: Explore, Local maps and Compare for "
            f"every city, as well as the reports and city briefings.\n\nSign in at {SITE} with {to}.\n\n"
            f"TheParkingAnalysts measures how full Europe's car parks are, from live city and operator feeds.\n")
    page = (f"<p>{html.escape(hello)}</p><p>Your sign-up to <b>TheParkingAnalysts</b> has been approved. You now have full access: Explore, "
            f"Local maps and Compare for every city, as well as the reports and city briefings.</p>"
            f'<p><a href="{SITE}" style="display:inline-block;padding:10px 18px;background:#1d4f9c;color:#fff;text-decoration:none;border-radius:4px">Sign in</a></p>'
            f"<p>Use {html.escape(to)}.</p>"
            f"<p style='color:#6e7886'>TheParkingAnalysts measures how full Europe's car parks are, from live city and operator feeds.</p>")
    return send(to, "Your TheParkingAnalysts sign-up is approved", text, page)


def new_signup(admin: str, who: str) -> tuple[bool, str | None]:
    """Told to the administrator when someone signs up and is waiting for approval."""
    text = (f"{who} has signed up to TheParkingAnalysts and is waiting for approval.\n\n"
            f"To give them full access, open {SITE}/#admin and choose Approve. Until then they see the guest view (reports, city "
            f"briefings and the sample cities). If you do not recognise the address, choose Reject.\n")
    return send(admin, f"Sign-up waiting for approval: {who}", text)
