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
source says it is. Refresh each quarter. Researched 2026-10-06: Düsseldorf, Dresden, Bielefeld,
Osnabrück, Frankfurt, Amsterdam. Not yet researched: Hamburg and the other cities.
