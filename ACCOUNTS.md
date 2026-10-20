# Accounts: Kinde sign-in, members and guests, Brevo emails

Sign-in is Kinde's (OpenID Connect, authorization code with PKCE). What a person may see is decided here
(`accounts.py`, a small SQLite file `accounts.db` on the Fly volume).

| Visitor | Sees |
|---|---|
| Guest (not signed in, or signed up but not yet approved) | Overview and live map, the three reports (utilisation, trends, yield), every city's written briefing, and Explore / Local maps / Compare for the **sample cities** only |
| Member (signed up and approved) | everything, for every city |
| Administrator (`friedrich.demmer@gmail.com`, always, from `ADMIN_EMAIL`) | a member, plus the Admin page: approvals, members, sample cities |

Anyone can sign up (Kinde confirms their email with a code); a new sign-up is stored as *pending* and sees the
guest view until the administrator approves it on the Admin page. Rejecting disables the address. You are
emailed (Brevo) for every new sign-up, and the member is emailed on approval.

Sample cities start as Frankfurt, Dortmund, Dresden, Nürnberg and Mannheim: German cities with good measured data from
our own feeds, none of the cities whose data comes through the Mobilithek. Edit the list on the Admin page.

## Set-up (owner)

Kinde (kinde.com): create a **Back-end web** application.
- Allowed callback URL: `https://theparkinganalysts.com/callback`
- Allowed logout redirect URL: `https://theparkinganalysts.com/`
- Authentication: email code (or password) sign-in with **email verification on**: the site trusts the address Kinde reports.
- Note the domain (`https://<name>.kinde.com`), the client ID and the client secret.

Brevo (brevo.com): verify a sender on your own domain (Brevo needs DKIM/SPF for the domain; a Gmail address cannot be
authenticated) and create an API key (SMTP & API > API keys). Optionally use Brevo's SMTP as Kinde's own email provider so
Kinde's codes also come from your domain.

Fly secrets (names only here; set them yourself):

    flyctl secrets set KINDE_DOMAIN=https://<name>.kinde.com KINDE_CLIENT_ID=... KINDE_CLIENT_SECRET=... --app parking-utilisation
    flyctl secrets set BREVO_API_KEY=... BREVO_SENDER_EMAIL=noreply@yourdomain BREVO_SENDER_NAME="TheParkingAnalysts" --app parking-utilisation
    flyctl secrets set APP_SECRET="$(openssl rand -base64 32)" --app parking-utilisation

Optional: `SITE_URL` (default `https://theparkinganalysts.com`), `ADMIN_EMAIL`.

## Modes

`kinde` when the three Kinde secrets are set. `password` (the old shared `SITE_PASSWORD`) while they are not: whoever
enters it is a member (header link "Member sign-in"). Remove `SITE_PASSWORD` and the password code once you have signed
in through Kinde. `none` when neither is set: everyone is a guest.

## Checks

`python3 test_access.py` (needs Flask; run in a throwaway venv) signs people in through a stand-in for Kinde and checks
guest, pending, member and administrator against every city-scoped endpoint of the real app.
