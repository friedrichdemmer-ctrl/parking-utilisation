"""Agent-based parking simulator, ported from the former parkingsimulator project.

The engine (demand generation by segment, multinomial-logit garage choice, tariff
and capacity allocation, hourly orchestration) is the original, unchanged in what
it computes: check_parity.py reproduces that project's archived Dusseldorf results
byte for byte. What is new is everything around it, so it runs on any city of the
competitive set: city.py builds a city's garages from the data and fills what the
data lacks, calibrate.py sets demand from measured occupancy where we have it, and
run_all.py runs every city. See README.md for the method and, as importantly, its limits.
"""
