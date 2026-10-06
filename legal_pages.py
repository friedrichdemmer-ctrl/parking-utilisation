"""The privacy notice (/privacy) and legal page (/legal), written for UK law.

- Privacy notice: UK GDPR Articles 13-14 and the Data Protection Act 2018. It describes what the
  site actually does (checked 2026-10-06): no cookies, no analytics; the Compare list kept in the
  visitor's own browser (localStorage, exempt under PECR as strictly necessary for a feature the
  visitor asked for); fonts from Google, map code from cdnjs (Cloudflare) and map tiles from Esri,
  which see visitors' IP addresses; analysis requests stored for 12 months (requests_store.py).
  If any of that changes, change the notice.
- Legal page: the information the Electronic Commerce (EC Directive) Regulations 2002 reg. 6
  require (name, geographic address, email; company number, VAT number where they apply; the
  Companies Act trading disclosures for a company), plus short terms of use.

The operator's details come from legal.json. Neither page is served until legal_name, address and
email are set (ready()), so an incomplete notice is never published.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import requests_store

LEGAL_PATH = Path(__file__).resolve().parent / "legal.json"
REQUIRED = ("legal_name", "address", "email")


def load() -> dict:
    return json.loads(LEGAL_PATH.read_text(encoding="utf-8")) if LEGAL_PATH.exists() else {}


def ready(legal: dict | None = None) -> bool:
    legal = legal if legal is not None else load()
    return all((legal.get(k) or "").strip() for k in REQUIRED)


def _e(v) -> str:
    return html.escape(str(v or ""))


def _when(legal: dict) -> str:
    try:
        return date.fromisoformat(legal.get("last_updated")).strftime("%-d %B %Y")
    except (TypeError, ValueError):
        return ""


def _operator(legal: dict) -> str:
    name = _e(legal["legal_name"])
    trading = _e(legal.get("trading_name") or "TheParkingAnalysts")
    who = f"{name}, trading as {trading}" if trading and trading != name else name
    lines = [f"<p><b>{who}</b><br>{_e(legal['address']).replace(chr(10), '<br>')}<br>"
             f'Email: <a href="mailto:{_e(legal["email"])}">{_e(legal["email"])}</a></p>']
    extra = []
    if legal.get("entity") == "company":
        if legal.get("company_number"):
            extra.append(f"Registered in {_e(legal.get('governing_law') or 'England and Wales')}, company number {_e(legal['company_number'])}")
        if legal.get("registered_office"):
            extra.append(f"Registered office: {_e(legal['registered_office'])}")
    if legal.get("vat_number"):
        extra.append(f"VAT number: {_e(legal['vat_number'])}")
    if legal.get("ico_registration"):
        extra.append(f"Registered with the Information Commissioner's Office, reference {_e(legal['ico_registration'])}")
    if extra:
        lines.append("<p>" + "<br>".join(extra) + "</p>")
    return "".join(lines)


def privacy(legal: dict) -> str:
    keep = requests_store.RETENTION_DAYS // 30
    email = _e(legal["email"])
    return f"""
<h1>Privacy notice</h1>
<p class="lede">How TheParkingAnalysts uses personal information, and your rights under UK data protection law. Last updated {_when(legal)}.</p>

<h2>Who is responsible</h2>
<p>The controller of your personal information is:</p>
{_operator(legal)}
<p>For anything in this notice, write to the email address above.</p>

<h2>The parking data</h2>
<p>The occupancy, capacity and price figures on this site describe car parks, not people. They come from public open-data feeds and operators' published tariffs and contain no personal information.</p>

<h2>Visiting the site</h2>
<p>We do not use cookies, analytics, tracking or advertising.</p>
<p>When your browser loads a page, our hosting provider receives the technical details every web request carries, such as your IP address, browser type and the page requested. We use these only to deliver the site, keep it secure and limit abuse. Our server keeps your IP address in memory for no more than a few minutes to stop anyone overloading the site, and does not write it to any log or database.</p>
<p>To display the pages, your browser also fetches files directly from three other services, which receive your IP address and browser details when it does: fonts from Google Fonts (Google), the map software from cdnjs (Cloudflare), and map images from Esri. Each handles that information under its own privacy policy.</p>
<p>If you use Compare, the list of cities and garages you choose is kept in your own browser's storage so it is still there next time. It is never sent to us, and you can clear it at any time in your browser settings. Because it only provides a feature you asked for, it needs no consent.</p>

<h2>When you ask us for an analysis</h2>
<p>If you use the "Ask us" form we keep what you enter: the kind of analysis, the place, your question, your email address and, if you give them, your name and organisation. We also keep a scrambled code derived from your IP address, which cannot be turned back into the address, to stop the form being abused.</p>
<p>We use this only to answer your request and, if you want, to discuss and carry out the work. Our lawful basis is that you have asked us to take these steps before any agreement (UK GDPR Article 6(1)(b)); for the abuse-prevention code it is our legitimate interest in keeping the form usable (Article 6(1)(f)).</p>
<p>When a request arrives we receive a short notification on our phone through the ntfy service. It contains only the request number, the kind of analysis and the place, never your email address or question.</p>
<p>Requests are deleted automatically after {keep} months, or sooner if you ask. If we go on to work together, the records we need for that work and for tax are kept as long as the law requires.</p>

<h2>Who else sees it</h2>
<p>We do not sell or share your information. It is stored by our hosting provider, Fly.io, Inc., on servers in Frankfurt, Germany, under a data processing agreement; the UK recognises the EU as giving adequate protection. Fly.io is based in the United States and takes part in the UK Extension to the EU–US Data Privacy Framework (the UK–US data bridge), which covers any access from there. When we reply by email, the reply passes through our email provider.</p>

<h2>Your rights</h2>
<p>You can ask us for a copy of the information we hold about you, and to correct it, delete it, restrict how we use it, object to how we use it, or receive it in a portable format. Email <a href="mailto:{email}">{email}</a>; we reply within one month. There is no charge.</p>
<p>If you are unhappy with how we have used your information, please tell us first. You also have the right to complain to the Information Commissioner's Office: <a href="https://ico.org.uk/make-a-complaint/" rel="noopener">ico.org.uk/make-a-complaint</a>, telephone 0303 123 1113.</p>

<h2>Changes</h2>
<p>If we change how we use personal information, we will update this notice and the date at the top.</p>
"""


def legal_page(legal: dict) -> str:
    law = _e(legal.get("governing_law") or "England and Wales")
    return f"""
<h1>Legal information and terms of use</h1>
<p class="lede">Who runs this site, and the terms on which the information is provided. Last updated {_when(legal)}.</p>

<h2>Who we are</h2>
{_operator(legal)}

<h2>Using the information</h2>
<p>The figures on this site are measured from public data feeds and operators' published information, and some are estimates that are labelled as such. They are provided for general information. Feeds can be wrong, late or interrupted, tariffs change, and written briefings describe the position on the date they give. Please check anything important before relying on it, and do not use the site as the only basis for an investment, pricing or planning decision.</p>
<p>We are not responsible for losses arising from reliance on the information, except where the law does not allow that responsibility to be limited, for example for death or personal injury caused by negligence or for fraud.</p>
<p>Links to other websites are provided for convenience; we are not responsible for their content.</p>

<h2>Our content</h2>
<p>The text, analysis and design of this site are ours. You may quote short extracts with a link to the page. Please do not copy or scrape the site's data in bulk; the interfaces are rate-limited for that reason. If you need data for your own work, <a href="/#ask">ask us</a>.</p>

<h2>Data sources</h2>
<p>Occupancy, capacity and tariff information comes from public open-data portals, transport authorities and operators, used under their own licences. Map images are © Esri and its data providers, including © OpenStreetMap contributors.</p>

<h2>Privacy</h2>
<p>How we handle personal information is explained in the <a href="/privacy">privacy notice</a>.</p>

<h2>Law</h2>
<p>These terms are governed by the law of {law}, and the courts of {law} have jurisdiction, without affecting any rights you have as a consumer where you live.</p>
"""


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · TheParkingAnalysts</title><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap">
<style>
:root {{ --bg:#f5f7fa; --surface:#fff; --ink:#111720; --ink-2:#4a5462; --ink-3:#6e7886; --rule:#dce1e8; --accent:#1d4f9c;
  --font-display:"Barlow Semi Condensed","Arial Narrow",Arial,sans-serif; --font-body:"Barlow","Helvetica Neue",Arial,sans-serif; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#0e1218; --surface:#151b23; --ink:#edf1f6; --ink-2:#b4bdc9; --ink-3:#8a94a2; --rule:#2a323d; --accent:#6b9ae6; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#0e1218; --surface:#151b23; --ink:#edf1f6; --ink-2:#b4bdc9; --ink-3:#8a94a2; --rule:#2a323d; --accent:#6b9ae6; color-scheme:dark; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:400 1rem/1.6 var(--font-body); }}
.wrap {{ max-width:44rem; margin:0 auto; padding:2.5rem max(16px,4vw) 4rem; display:grid; gap:.9rem; }}
h1 {{ font:700 clamp(2rem,4.5vw,2.8rem)/1.1 var(--font-display); margin:0; text-wrap:balance; }}
h2 {{ font:600 1.3rem var(--font-display); margin:1.4rem 0 0; }}
p {{ margin:0; }} .lede {{ color:var(--ink-2); font-size:1.08rem; }}
a {{ color:var(--accent); }}
</style></head><body>{bar}<div class="wrap">{body}</div></body></html>"""
