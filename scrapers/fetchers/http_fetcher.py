"""Plain HTTP fetcher for static/JSON sources -- no browser needed.

Stdlib only (urllib), consistent with the rest of this project: no extra
dependency for the common case, since most sources we've found (government
open-data JSON/WFS feeds) don't need JS rendering.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

USER_AGENT = "parking-utilisation-scraper/1.0 (research project, low-volume, polite)"


class HttpFetcher:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def get_json(self, url: str, headers: dict[str, str] | None = None):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)


class FetchError(Exception):
    pass
