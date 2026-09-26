"""Shared helpers for adapters -- notably name normalization, reused from the
manual matching logic in apply_capacity_overrides.py's research scripts so
adapters and one-off backfills use the same rules.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_name(s: str | None) -> str:
    s = s or ""
    s = re.sub(r"\(.*?\)", "", s)  # strip parenthetical suffixes like "(*)" "(geschlossen)"
    s = s.lower()
    s = s.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def archive_slug(name: str) -> str:
    """The defgsus community archive's place_id suffix: ASCII-folded name, case
    kept, runs of non-alphanumerics as "-" (e.g. "Hörster Platz" ->
    "Horster-Platz"). Adapters that continue an archive source's history
    must build place_ids the same way."""
    s = unicodedata.normalize("NFKD", name.replace("ß", "ss"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
