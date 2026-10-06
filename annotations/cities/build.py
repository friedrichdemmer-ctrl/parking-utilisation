#!/usr/bin/env python3
"""Turn researched drafts into publishable city notes.

    python3 annotations/cities/build.py

For each <slug>.draft.json that has a <slug>.verdict.json (an independent fact-check that re-opened
every source), write <slug>.json containing only what survived:

  supported    kept as written (with a corrected title/date if the checker gave one)
  partly       kept with the checker's corrected_text, which holds only what the page supports
  unsupported / unreachable / confidence "low"   dropped (counted in "dropped")

A draft with no verdict file is NOT published. The draft and verdict files stay in the repo as the
audit trail; only <slug>.json is served (see city_briefing.notes). Rerun after a new draft or verdict.
"""

import json
from datetime import date
from pathlib import Path

DIR = Path(__file__).resolve().parent


def build(draft_path: Path) -> dict | None:
    slug = draft_path.name.removesuffix(".draft.json")
    verdict_path = DIR / f"{slug}.verdict.json"
    if not verdict_path.exists():
        print(f"{slug}: no verdict file, not published")
        return None
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    by_index = {v["index"]: v for v in verdict["items"]}
    kept, dropped = [], {"unsupported": 0, "unreachable": 0, "low confidence": 0, "unchecked": 0}
    for i, item in enumerate(draft["items"]):
        v = by_index.get(i)
        if v is None:
            dropped["unchecked"] += 1
            continue
        if v["verdict"] in ("unsupported", "unreachable"):
            dropped[v["verdict"]] += 1
            continue
        if item["confidence"] == "low":
            dropped["low confidence"] += 1
            continue
        out = dict(item, id=i)                # the draft index: stable, so narratives can cite it as [i]
        if v["verdict"] == "partly":
            if not v.get("corrected_text"):
                dropped["unsupported"] += 1
                continue
            out["text"] = v["corrected_text"]
            out["confidence"] = "medium" if out["confidence"] == "high" else out["confidence"]
        if v.get("corrected_title"):
            out["source_title"] = v["corrected_title"]
        if v.get("corrected_date"):
            out["date"] = v["corrected_date"]
        out["checked"] = v["verdict"]
        kept.append(out)
    result = {
        "country": draft["country"], "city": draft["city"], "researched": draft["researched"], "verified": date.today().isoformat(),
        "summary": verdict.get("corrected_summary") or draft["summary"],
        "items": kept, "gaps": draft.get("gaps", []),
        "dropped": {k: n for k, n in dropped.items() if n},
    }
    (DIR / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{slug}: {len(kept)} of {len(draft['items'])} items kept; dropped {result['dropped'] or 'none'}")
    return result


if __name__ == "__main__":
    for path in sorted(DIR.glob("*.draft.json")):
        build(path)
