# Simulator

An agent-based model of one weekday in a city's parking market, ported from the former
`parkingsimulator` project (Düsseldorf, Q-Park pricing) so it runs on every city in
`competitive/`. Archived original: `archive/parkingsimulator/`.

    python3 -m simulator.check_parity      # engine still reproduces the archived Düsseldorf results
    python3 -m simulator.targets <util.json>   # refresh calibration_targets.json from a utilisation report
    python3 -m simulator.run_all --jobs 6  # re-run every city -> simulator/results/*.json  (~2 min)

Results are files, read by `/api/sim/city` and shown under the map on the Local maps page.
Nothing is simulated at request time.

## How it works

Eight demand segments (commuters, shoppers, ...) arrive hour by hour. Each arrival chooses a
garage by multinomial logit over distance, price × segment price sensitivity, quality, app/ANPR,
EV charging, an operator-network bonus and a capacity-pressure term; stays have a random
length; the garage fills and empties; takings are the price paid (hourly rate capped at the day
ticket). Engine files (`models`, `geo`, `tariffs`, `choice`, `demand`, `allocation`, `engine`)
are the original's maths; the only changes are that garages are passed in rather than read from
a CSV, a price is computed once per garage and segment per run (not per arrival), and optional
`contract_floor` (default 0 = the original). `check_parity` proves the results are unchanged.

## What is new

| | |
|---|---|
| `city.py` | builds a city's garages from the competitive set. Zone and quality are derived from distance to the centre, app flag from operator size; missing capacity/tariff/day ticket filled with the city, then country median (flagged per garage). DKK and GBP converted to EUR at fixed rates. Needs ≥5 garages, ≥3 with a capacity, ≥3 with a tariff (182 cities; the rest are listed in `results/index.json` under `skipped`). |
| `calibrate.py` | fits one demand factor and the overnight contract share per city to measured occupancy; validation helpers |
| `targets.py` | measured weekday 06–21 profiles from the utilisation report |
| `scenarios.py` | price ±20% / +50%, core price cap at the city's median, 30% of core spaces closed, EV surge |
| `run_all.py` | fits, runs all scenarios over 5 seeds, leave-one-city-out validation |

Calibration has three tiers: **garage** (≥3 listed garages we also measure: simulated occupancy of
exactly those is matched), **city** (≥3 measured garages in the city: city-wide level matched),
**transferred** (nothing measured: the median factor of the fitted cities).

## What it cannot tell you (stated on the page too)

1. **No outside option.** Every arriving driver parks somewhere, so prices and closures only move
   drivers between garages; sessions barely change and revenue follows price almost mechanically.
   (Our own tariffs-vs-occupancy data, r = +0.18 across ~270 tariffs, says occupancy is also
   insensitive to price, which is why this is not absurd, but it is not evidence of elasticity.)
2. **Level is not predicted.** Leave-one-city-out, 24 fitted cities: simulated occupancy is a median
   ~11 points off, the same as guessing the average measured level; the correlation across cities
   between simulated and measured level is negative (−0.55), because demand is assumed ∝ capacity.
   Transferred cities are labelled *illustrative*: read the scenario deltas, not the totals.
3. **Which garage is busy is weakly captured.** Median garage-level correlation ≈ 0.14–0.2 over the
   8–9 cities with ≥3 measured listed garages; the daily rhythm is good (≈ 0.8).
4. Zones, quality and app flags are derived, not judged on site; `member_discount_pct` in the
   original is dead code (`is_member` is always False) and was left as is.
5. One weekday; no seasons, events or weekends (the engine supports a weekend profile, not run).

Marseille's fit hits the lower bound of the demand range (its measured night occupancy is too
high for the model to start below); it is flagged `reached_target: false` and excluded from the
transferred factor.
