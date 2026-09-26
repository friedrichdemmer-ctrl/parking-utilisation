"""Plain HTTP fetcher for static/JSON sources -- no browser needed.

Stdlib only (urllib), consistent with the rest of this project: no extra
dependency for the common case, since most sources we've found (government
open-data JSON/WFS feeds) don't need JS rendering.
"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request

USER_AGENT = "parking-utilisation-scraper/1.0 (research project, low-volume, polite)"


class HttpFetcher:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def _read_body(self, resp) -> bytes:
        # Some CDNs (observed for data.strasbourg.eu, only from Fly's fra
        # egress -- not reproducible from this project's dev network) gzip
        # the body without a declared Content-Encoding header, so gzip-magic
        # sniffing is the only reliable way to catch it.
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return self._read_body(resp)

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return self._read_body(resp).decode("utf-8", errors="replace")

    def get_json(self, url: str, headers: dict[str, str] | None = None):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(self._read_body(resp))


class FetchError(Exception):
    pass
