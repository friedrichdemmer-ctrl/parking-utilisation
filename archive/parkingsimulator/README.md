# parkingsimulator (archived)

A copy of github.com/friedrichdemmer-ctrl/parkingsimulator at commit `d7ac533` (2026-10-05),
kept so that repository can be retired. Nothing here is wired into the site.

- The competitive dataset and its research notes moved to `../../competitive/` and are used by the
  site's "Local maps" section, which replaces this project's Streamlit app (`app.py`).
- `src/` is the Düsseldorf agent-based simulator: demand generation by segment, a multinomial-logit
  garage choice model (distance decay, price, quality, EV, capacity pressure), tariff and allocation
  engines, and hourly orchestration. `outputs/` holds its four scenarios (baseline, price +20%,
  regulation shock, CBD capacity shock) and the Q-Park relative-performance table.
- `data/assets.csv` is the 42-garage Düsseldorf asset file the simulator reads, with the fields the
  competitive set lacks (zone, member discount, app/ANPR flags, a quality score).
- `scripts/export_europe.py` generated the Europe-wide export from the per-city CSVs; the export is
  lossless (3,839 city rows + 42 Düsseldorf rows = 3,881).

Not on GitHub, and so not here: the project's OneDrive folder
(`Programming/parkingsimulator`) also holds `BUILD_SUMMARY.md`, `DB API.md`, `START_HERE.txt` and two
PDFs (`Duesseldorf_Parking_Simulation_Handoff.pdf`, `Q-Park_Parking_Optimizer_Demonstrator.pdf`).
Keep that folder, or copy those five files in, before deleting it.
