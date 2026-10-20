# Accounts: Kinde sign-in, roles, Brevo emails

Sign-in is Kinde's (OpenID Connect, authorization code with PKCE). What a person may do is decided here
(`accounts.py`, a small SQLite file `accounts.db` on the Fly volume): a Kinde login alone gives nothing; the
email address must have been invited by the administrator.

| Role | Sees |
|---|---|
| Administrator (`friedrich.demmer@gmail.com`, always, from `ADMIN_EMAIL`) | everything, plus the Admin page (users, cities) |
| Full user | Explore, Local maps, Compare, Reports and city briefings, for every city |
| Demonstrator | the same, for the cities on the allowed list only (Admin page > Cities); the reports cover all cities |

Public, as before: the Overview and its live map, the Feeds page, the legal pages.

## Set-up (owner)

Kinde (kinde.com): create a **Back-end web** application.
- Allowed callback URL: `https://theparkinganalysts.com/callback`
- Allowed logout redirect URL: `https://theparkinganalysts.com/`
- Under Authentication, use email code (or password) sign-in with **email verification on**: the site trusts the
  address Kinde reports, so Kinde must have confirmed it. Switch self-sign-up off if you want only invited people
  to be able to create a login at all (the site refuses uninvited addresses either way).
- Note the domain (`https://<name>.kinde.com`), the client ID and the client secret.

Brevo (brevo.com): verify a sender on your own domain (Brevo needs DKIM/SPF for the domain; a Gmail address
cannot be authenticated) and create an API key (SMTP & API > API keys). Optionally use Brevo's SMTP as Kinde's
own email provider so Kinde's codes also come from your domain.

Fly secrets (names only here; set them yourself):

    flyctl secrets set KINDE_DOMAIN=https://<name>.kinde.com KINDE_CLIENT_ID=... KINDE_CLIENT_SECRET=... --app parking-utilisation
    flyctl secrets set BREVO_API_KEY=... BREVO_SENDER_EMAIL=noreply@yourdomain BREVO_SENDER_NAME="TheParkingAnalysts" --app parking-utilisation
    flyctl secrets set APP_SECRET="$(openssl rand -base64 32)" --app parking-utilisation

Optional: `SITE_URL` (default `https://theparkinganalysts.com`), `ADMIN_EMAIL`.

## Modes

`kinde` when the three Kinde secrets are set. `password` (the old shared `SITE_PASSWORD`) while they are not:
everyone it admits is a full user. Remove `SITE_PASSWORD` and the password code once you have signed in through Kinde.
`none` when neither is set: the protected parts answer 503.

## Checks

`python3 test_access.py` (needs Flask; run in a throwaway venv) signs people in through a stand-in for Kinde and
checks every role and every city-scoped endpoint against the real app.
