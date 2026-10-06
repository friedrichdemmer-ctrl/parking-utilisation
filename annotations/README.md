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
