"""UK postcode <-> WGS84 lookups via postcodes.io (free, no key, built on
ONS / Ordnance Survey open data).

Only "not found" (HTTP 404) is treated as a miss. Any other failure
propagates, so a postcodes.io outage fails the capacity run (and it is
retried next cycle) instead of silently blanking stored coordinates.
"""

from __future__ import annotations

import urllib.error
import urllib.parse

API = "https://api.postcodes.io"


def _get(fetcher, url: str):
    try:
        return fetcher.get_json(url).get("result")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def lookup(fetcher, postcode: str) -> dict | None:
    """Full-postcode lookup, falling back to the district (outcode) centroid
    when only e.g. "LS28" is given or the full code is unknown."""
    pc = " ".join((postcode or "").upper().split())
    if not pc:
        return None
    if " " in pc:
        result = _get(fetcher, f"{API}/postcodes/{urllib.parse.quote(pc)}")
        if result:
            return result
    return _get(fetcher, f"{API}/outcodes/{urllib.parse.quote(pc.split()[0])}")


def nearest(fetcher, lat: float, lon: float) -> dict | None:
    """Nearest postcode to a coordinate, within 2km."""
    results = _get(fetcher, f"{API}/postcodes?lon={lon}&lat={lat}&radius=2000&limit=1")
    return results[0] if results else None
