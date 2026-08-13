"""Shared helpers for adapters -- notably name normalization, reused from the
manual matching logic in apply_capacity_overrides.py's research scripts so
adapters and one-off backfills use the same rules.
"""

from __future__ import annotations

import re


def normalize_name(s: str | None) -> str:
    s = s or ""
    s = re.sub(r"\(.*?\)", "", s)  # strip parenthetical suffixes like "(*)" "(geschlossen)"
    s = s.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s
