"""Read the batch results (simulator/results/*.json). No simulation happens at request time."""

import json
import re
from functools import lru_cache
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def slug(country: str, city: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{country}_{city}".lower().replace("ß", "ss")).strip("_")


@lru_cache(maxsize=1)
def index() -> dict | None:
    path = RESULTS / "index.json"
    return json.loads(path.read_text()) if path.exists() else None


@lru_cache(maxsize=1)
def validation() -> list[dict]:
    path = RESULTS / "validation.json"
    return json.loads(path.read_text()) if path.exists() else []


@lru_cache(maxsize=256)
def city(country: str, name: str) -> dict | None:
    path = RESULTS / f"{slug(country, name)}.json"
    return json.loads(path.read_text()) if path.exists() else None
