"""Parking feeds pulled from the Mobilithek (mobilithek.info), Germany's national mobility data portal.

A Mobilithek "pull" subscription is an HTTPS address that serves the provider's latest delivery. Access
needs the machine certificate issued for our machine account (mutual TLS): the Fly secrets MOBILITHEK_CERT
and MOBILITHEK_KEY hold it as PEM text. Two things a plain request gets wrong (found 2026-10-19):

- without the certificate the gateway answers 400 "No required SSL certificate was sent";
- with it, the pull still answers 406 unless the Accept header lists the XML types AND the request allows
  gzip, so both are sent below. 204 means the provider has delivered nothing yet (new subscription).

Each entry of FEEDS is one city's feed. The live counts are a DATEX II v2 publication; a ParkingFacility
Status carries only an id ("PH01"), the counts and a time, so the name, capacity and position come from the
provider's separate static offer ("..statisch") once that has been approved and delivered. Until then the
garage is named from Feed.places where a name could be established elsewhere, else "<City> PH01", and its
capacity is free + occupied from the live counts. A later weekly
capacity run replaces both with the static values.

Other publishers deliver other shapes (the NRW bundle is a JSON list of ParkingSite objects and was found
frozen at 2025-07-23); add a parser, not a new fetch path, when one is subscribed.

Readings are skipped when a count is negative (Magdeburg's PH02 reported -5 occupied) or the facility is
marked closed. The reading time is the facility's own status time, not the fetch time, so a feed that
stops updating shows as stale instead of being refreshed by our polling.
"""

from __future__ import annotations

import gzip
import os
import re
import ssl
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

PULL_URL = "https://mobilithek.info:8443/mobilithek/api/v1.0/subscription/{id}/clientPullService?subscriptionID={id}"
HEADERS = {"Accept": "application/xml, text/xml, application/json, */*", "Accept-Encoding": "gzip"}
SOURCE_WEB_URL = "https://mobilithek.info/"


@dataclass(frozen=True)
class Feed:
    source_id: str
    city: str
    dynamic: str                 # subscription id of the live-counts offer
    static: str | None = None    # subscription id of the static offer (names, capacities, positions)
    # ref -> (name, lat, lon): names from a source we could read, used while the static offer gives nothing
    places: dict = field(default_factory=dict)


# Magdeburg: the static offer ("Parkplätze Stadt Magdeburg") delivers an empty table (checked 2026-10-19), and the
# live feed names its car parks PH01.. only. The names come from the city's own parking-guidance page,
# movi.de/parkinfo (run with the Tiefbauamt Magdeburg), matched on 2026-10-19 at ~14:00 local by comparing its free
# counts and times with the feed: Universitätsplatz 110 free = PH01 110; Allee Center 828 = PH11 827; Hotel Maritim 328
# = PH06 327; Ulrichshaus 127 = PH07 126; Petriförder Ost 87 = PH09 85; Petriförder West 45 = PH10 45; Elbauenpark
# 846 = PH16 841; Domviertel 50 = PH18 50 (both stamped 06:00). PH02 and PH04 match no listed car park and stay
# unnamed. Coordinates are Nominatim's for the named place and approximate; none is given where the place is
# ambiguous (Petriförder Ost, Domviertel, Elbauenpark).
MAGDEBURG_PLACES = {
    "PH01": ("Universitätsplatz", 52.13892, 11.63956),
    "PH06": ("Hotel Maritim", 52.12933, 11.63205),
    "PH07": ("Ulrichshaus", 52.13048, 11.63530),
    "PH09": ("Petriförder Ost", None, None),
    "PH10": ("Petriförder West", 52.13276, 11.64586),
    "PH11": ("Allee-Center", 52.12998, 11.63754),
    "PH16": ("Elbauenpark P+R", None, None),
    "PH18": ("Domviertel", None, None),
}

FEEDS = [
    # Parkbelegungsdaten Stadt Magdeburg (ifak e.V.), approved 2026-10-19
    Feed("mobilithek-magdeburg", "Magdeburg", dynamic="1048961318253412352", static="1048961358375899136",
         places=MAGDEBURG_PLACES),
    # Parkdaten Stadt Köln dynamisch / statisch (Stadt Köln, DATEX II v2 parkingRecord), approved 2026-10-19: 41
    # records with names, counted capacities and coordinates. Written under its own place_ids, not into the
    # archive's koeln-apps-parken ones, because the counted capacity differs from the capacities on file for many
    # of them (Mediapark 430 vs 1,148, Dom 220 vs 520) and occupancy is only right against the feed's own count.
    Feed("mobilithek-koeln", "Köln", dynamic="1048984704203509760", static="1048985043690504192"),
]

_context: ssl.SSLContext | None = None


def _ssl_context() -> ssl.SSLContext:
    """The client-certificate context, built once from the Fly secrets. The PEM text is written to a private
    temporary directory only long enough to be loaded."""
    global _context
    if _context is None:
        cert, key = os.environ.get("MOBILITHEK_CERT"), os.environ.get("MOBILITHEK_KEY")
        if not cert or not key:
            raise RuntimeError("MOBILITHEK_CERT / MOBILITHEK_KEY are not set")
        ctx = ssl.create_default_context()
        with tempfile.TemporaryDirectory() as d:          # created 0700
            cp, kp = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
            for path, text in ((cp, cert), (kp, key)):
                with open(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
                    f.write(text)
            ctx.load_cert_chain(cp, kp)
        _context = ctx
    return _context


def pull(subscription_id: str, timeout: int = 60) -> bytes | None:
    """The provider's latest delivery for a subscription, or None when it has delivered nothing (204)."""
    req = urllib.request.Request(PULL_URL.format(id=subscription_id), headers=HEADERS)
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout) as resp:
        body = resp.read()
        if resp.status == 204 or not body:
            return None
        return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


# ---------------------------------------------------------------- parsing (pure, no network)

def _tag(e: ET.Element) -> str:
    return e.tag.rsplit("}", 1)[-1]


def _text(e: ET.Element, name: str) -> str | None:
    for c in e.iter():
        if _tag(c) == name and c.text and c.text.strip():
            return c.text.strip()
    return None


def _int(s: str | None) -> int | None:
    try:
        return int(float(s)) if s is not None else None
    except ValueError:
        return None


def _utc(iso: str) -> str:
    dt = datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp without an offset")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_status(xml: bytes) -> list[dict]:
    """DATEX II v2 parking status: [{ref, vacant, occupied, closed, ts (UTC ISO)}]. Two shapes occur:
    parkingFacilityStatus (Magdeburg, by ifak) and parkingRecordStatus (Köln). Facilities without a reference,
    counts or time are left out; "closed" is the facility's own opening status."""
    out = []
    for e in ET.fromstring(xml).iter():
        kind = _tag(e)
        if kind not in ("parkingFacilityStatus", "parkingRecordStatus"):
            continue
        ref_tag = "parkingFacilityReference" if kind == "parkingFacilityStatus" else "parkingRecordReference"
        refs = [c.attrib.get("id") for c in e if _tag(c) == ref_tag]
        if not refs:
            continue                        # the inner <parkingFacilityStatus>spacesAvailable</..> text elements
        vacant = _int(_text(e, "totalNumberOfVacantParkingSpaces") or _text(e, "parkingNumberOfVacantSpaces"))
        occupied = _int(_text(e, "totalNumberOfOccupiedParkingSpaces") or _text(e, "parkingNumberOfOccupiedSpaces"))
        when = _text(e, "parkingFacilityStatusTime") or _text(e, "parkingStatusOriginTime")
        states = {x.text.strip().lower() for x in e.iter() if _tag(x) in ("parkingFacilityStatus", "parkingSiteOpeningStatus") and x.text}
        if not refs[0] or vacant is None or occupied is None or not when:
            continue
        out.append({"ref": refs[0], "vacant": vacant, "occupied": occupied, "closed": "closed" in states, "ts": _utc(when)})
    return out


def parse_static(xml: bytes) -> dict[str, dict]:
    """DATEX II v2 parking table: {ref: {name, capacity, lat, lon}}. Köln's parkingRecord (parkingName,
    parkingNumberOfSpaces) is verified against a real delivery; the parkingFacility form (parkingFacilityName,
    totalParkingCapacity) follows the standard and has not been seen with content (Magdeburg's static table is
    empty). A facility with no capacity is returned with capacity None."""
    out = {}
    for e in ET.fromstring(xml).iter():
        if _tag(e) not in ("parkingRecord", "parkingFacility") or not e.attrib.get("id"):
            continue
        name = None
        for c in e:
            if _tag(c) in ("parkingName", "parkingFacilityName"):
                name = _text(c, "value") or (c.text or "").strip() or None
        lat, lon = _text(e, "latitude"), _text(e, "longitude")
        out[e.attrib["id"]] = {"name": name, "capacity": _int(_text(e, "totalParkingCapacity") or _text(e, "parkingNumberOfSpaces")),
                               "lat": float(lat) if lat else None, "lon": float(lon) if lon else None}
    return out


def _slug(ref: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")


# ---------------------------------------------------------------- the adapter

class MobilithekPullAdapter(SourceAdapter):
    fetcher_type = "http"                   # unused: the Mobilithek needs the client certificate (see pull())
    occupancy_interval_seconds = 15 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def __init__(self, feed: Feed, pull_fn=pull):
        self.feed = feed
        self.name = feed.source_id
        self._pull = pull_fn

    def place_id(self, ref: str) -> str:
        return f"{self.feed.source_id}-{_slug(ref)}"

    def _static(self) -> dict[str, dict]:
        if not self.feed.static:
            return {}
        body = self._pull(self.feed.static)
        return parse_static(body) if body else {}

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        body = self._pull(self.feed.dynamic)
        if not body:
            return []
        static = self._static()
        records = []
        for s in parse_status(body):
            known = self.feed.places.get(s["ref"])
            meta = static.get(s["ref"]) or ({"name": known[0], "lat": known[1], "lon": known[2]} if known else {})
            capacity = meta.get("capacity") or (s["vacant"] + s["occupied"] if s["vacant"] >= 0 and s["occupied"] >= 0 else 0)
            if capacity <= 0:
                continue
            records.append(CapacityRecord(
                place_id=self.place_id(s["ref"]), place_name=meta.get("name") or f"{self.feed.city} {s['ref']}",
                city_name=self.feed.city, num_all=capacity, source_id=self.name,
                latitude=meta.get("lat"), longitude=meta.get("lon"), source_web_url=SOURCE_WEB_URL))
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        body = self._pull(self.feed.dynamic)
        if not body:
            return []
        return [OccupancyRecord(place_id=self.place_id(s["ref"]), ts=s["ts"], free=s["vacant"])
                for s in parse_status(body) if s["vacant"] >= 0 and s["occupied"] >= 0 and not s["closed"]]


def mobilithek_adapters() -> list[MobilithekPullAdapter]:
    return [MobilithekPullAdapter(f) for f in FEEDS]
