"""Checks for scrapers/adapters/mobilithek_pull.py against a real Magdeburg delivery (2026-10-19).

    python3 scrapers/test_mobilithek_pull.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import import_historical
from scrapers import storage
from scrapers.adapters import mobilithek_pull as m
from scrapers.validate import filter_valid

STATUS = (ROOT / "scrapers/fixtures/mobilithek_magdeburg_status.xml").read_bytes()
STATIC = b"""<d2LogicalModel xmlns="http://datex2.eu/schema/2/2_0"><payloadPublication><parkingFacilityTable>
<parkingFacility id="PH01"><parkingFacilityName><values><value lang="de">Parkhaus Allee-Center</value></values></parkingFacilityName>
<totalParkingCapacity>125</totalParkingCapacity><parkingFacilityLocation><pointByCoordinates><pointCoordinates>
<latitude>52.1306</latitude><longitude>11.6428</longitude></pointCoordinates></pointByCoordinates></parkingFacilityLocation></parkingFacility>
</parkingFacilityTable></payloadPublication></d2LogicalModel>"""

feed = m.FEEDS[0]
calls = []


def fake_pull(sub_id):
    calls.append(sub_id)
    return STATIC if sub_id == feed.static else STATUS


# --- parsing the real delivery
rows = m.parse_status(STATUS)
assert len(rows) == 10, len(rows)
ph01 = next(r for r in rows if r["ref"] == "PH01")
assert (ph01["vacant"], ph01["occupied"], ph01["ts"]) == (110, 10, "2026-10-19T11:45:00+00:00"), ph01   # 13:45 +02:00
assert next(r for r in rows if r["ref"] == "PH02")["occupied"] == -5

# --- occupancy: the -5 facility is dropped, times are UTC, free = vacant
a = m.MobilithekPullAdapter(feed, pull_fn=fake_pull)
occ = a.fetch_occupancy(None, {})
assert len(occ) == 9 and all(o.ts.endswith("+00:00") for o in occ)
assert a.place_id("PH01") == "mobilithek-magdeburg-ph01"
assert {o.place_id for o in occ}.isdisjoint({"mobilithek-magdeburg-ph02"})

# --- capacity: the static offer (names, capacity, position) wins; without it free + occupied
with_static = {c.place_id: c for c in a.fetch_capacity(None)}
assert with_static["mobilithek-magdeburg-ph01"].place_name == "Parkhaus Allee-Center"
assert with_static["mobilithek-magdeburg-ph01"].num_all == 125 and with_static["mobilithek-magdeburg-ph01"].latitude == 52.1306
assert with_static["mobilithek-magdeburg-ph04"].num_all == 187            # 27 + 160, no static entry
assert with_static["mobilithek-magdeburg-ph04"].place_name == "Magdeburg PH04"
assert "mobilithek-magdeburg-ph02" not in with_static                      # a negative count gives no capacity
assert with_static["mobilithek-magdeburg-ph11"].place_name == "Allee-Center"          # from Feed.places, no static entry
assert with_static["mobilithek-magdeburg-ph11"].num_all == 1300 and with_static["mobilithek-magdeburg-ph11"].latitude == 52.12998
assert with_static["mobilithek-magdeburg-ph16"].place_name == "Elbauenpark P+R" and with_static["mobilithek-magdeburg-ph16"].latitude is None
empty = m.MobilithekPullAdapter(feed, pull_fn=lambda sid: None if sid == feed.static else STATUS)
assert {c.place_id: c.place_name for c in empty.fetch_capacity(None)}["mobilithek-magdeburg-ph04"] == "Magdeburg PH04"   # unmatched stays a placeholder
assert m.MobilithekPullAdapter(feed, pull_fn=lambda sid: None).fetch_occupancy(None, {}) == []   # nothing delivered yet

# --- through the real storage and validation layers
conn = sqlite3.connect(":memory:")
conn.executescript(import_historical.SCHEMA)   # lots_meta and historical_observations, as in production
storage.ensure_schema(conn)
storage.write_capacity(conn, a.fetch_capacity(None))
caps = storage.known_capacities_for_source(conn, a.name)
valid, rejected = filter_valid(occ, caps)
assert len(valid) == 9 and not rejected, rejected
assert storage.write_occupancy(conn, valid) == 9
assert storage.write_occupancy(conn, valid) == 0                           # the same delivery again adds nothing
# --- Köln (parkingRecord flavour, real delivery of 2026-10-19)
KS = (ROOT / "scrapers/fixtures/mobilithek_koeln_status.xml").read_bytes()
KT = (ROOT / "scrapers/fixtures/mobilithek_koeln_static.xml").read_bytes()
kfeed = next(f for f in m.FEEDS if f.source_id == "mobilithek-koeln")
k = m.MobilithekPullAdapter(kfeed, pull_fn=lambda sid: KT if sid == kfeed.static else KS)
kc = {c.place_id: c for c in k.fetch_capacity(None)}
assert len(kc) == 40, len(kc)                                      # 41 records; PH01 has no capacity at all
g = kc["mobilithek-koeln-ph19"]
assert (g.place_name, g.num_all, g.city_name, round(g.latitude, 4)) == ("Am Gürzenich", 300, "Köln", 50.937), g
ko = {o.place_id: o for o in k.fetch_occupancy(None, {})}
assert ko["mobilithek-koeln-ph19"].free == 183 and ko["mobilithek-koeln-ph19"].ts == "2026-10-19T12:13:50+00:00"
assert not any("w-p" in pid for pid in ko), "stadium car parks marked closed must not give readings"
assert "mobilithek-koeln-d-p004" in ko and ko["mobilithek-koeln-d-p004"].free == 0   # a full car park is a reading, not an error
kconn = sqlite3.connect(":memory:")
kconn.executescript(import_historical.SCHEMA)
storage.ensure_schema(kconn)
storage.write_capacity(kconn, list(kc.values()))
kvalid, krej = filter_valid(list(ko.values()), storage.known_capacities_for_source(kconn, k.name))
assert not krej, krej
print("mobilithek_pull: all checks passed")
