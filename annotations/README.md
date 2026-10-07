# Annotations

`events.csv` is the hand-kept list of dated events that the trends page marks on its charts.

- One row per event; `start`/`end` are `YYYY-MM` or `YYYY-MM-DD` (end blank = still in force).
- `scope`: `DE`, `EU`, `all`. The overall index is ~95% German capacity until 2026 (see the
  composition note on /trends), so German events are the ones that can explain it.
- `kind`: health, transport, fuel, economy, structural, data.
- `measure=yes`: `trends_report.py` also computes the step in the seasonally adjusted index
  over the three months after the start against the three before, and says whether it is
  distinguishable from normal month-to-month movement. `no` for gradual events (a recovery
  that follows a lockdown is not a "step at the start").
- Every row carries a source and a `confidence`. Say what a source says; never attribute a
  movement to an event on the strength of timing alone.
- Review the list when the trends report is rebuilt each quarter and add new policy changes.

## City context (`cities/`)

Per-city notes shown in the city briefing on Explore (city_briefing.py, /api/briefing).

1. A researcher writes `<country>_<city>.draft.json`: dated items with topic, source URL/title and a
   confidence, from sources it actually opened (never from memory).
2. A SEPARATE fact-check re-opens every source and writes `<country>_<city>.verdict.json`
   (supported / partly / unsupported / unreachable, with corrected text, title, date).
3. `python3 annotations/cities/build.py` writes the published `<country>_<city>.json`: supported items
   as written, "partly" items with the checker's corrected text, everything else dropped. A draft
   without a verdict file is never published.

Drafts and verdicts stay in the repo as the audit trail but are kept out of the Docker image.
Proposals, plans and forecasts must stay worded as such; never state a price as in force unless the
source says it is. Refresh each quarter. Researched and written 2026-10-06 (30 cities): Düsseldorf, Dresden, Bielefeld, Osnabrück, Frankfurt,
Amsterdam, Hamburg, Nürnberg, Lyon, Heidelberg, Zürich, Basel, Bordeaux, Mannheim, Münster, Torino,
Nantes, Strasbourg, Dortmund, Freiburg, Karlsruhe, Heilbronn, Madrid, Marseille, Salzburg, Luxembourg, Bolzano, Jena, Bochum, Bonn.
Candidates next: Lille, Vigo, Firenze, Kassel, Augsburg, Leipzig.
Sources a page itself labels as AI-written are not cited (Torino's via Roma item).


### Unconfirmed claims and unreadable sources (rule set by the owner, 2026-10-06)

- Never invent or round up a claim. If a source cannot be opened or read in full, the claim is NOT
  presented as fact: the fact-check marks it `unreachable`, and `build.py` publishes it only as an
  "unconfirmed" item (shown under "Reported, but not confirmed" with the reason and the link), worded as
  what a search result says. Narrative text never cites an unconfirmed item.
- Items the checker could read only in part (paywall, login, registration wall) are published with the
  note "only the headline and opening could be read".
- Where a PDF is unreadable, give the owner the link; the owner investigates and uploads the document to
  `annotations/cities/uploads/` (see the README there). Then re-check the item against the upload.
- Verifier prompts must say: do not accept a search snippet as confirmation; mark the item unreachable;
  give `unconfirmed_text` and `unconfirmed_reason` for it.
