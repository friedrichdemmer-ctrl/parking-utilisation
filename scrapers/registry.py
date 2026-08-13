"""Registered adapters. Add a new source by importing it and appending an
instance here -- nothing else needs to change to wire it into the runner.
"""

from __future__ import annotations

from scrapers.adapters.koeln_live import KoelnLiveAdapter
from scrapers.base import SourceAdapter

ADAPTERS: list[SourceAdapter] = [
    KoelnLiveAdapter(),
]
