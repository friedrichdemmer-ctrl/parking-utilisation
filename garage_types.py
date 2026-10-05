"""Car-park type from the garage's name.

No source says what a car park serves, but names usually do: "Galerie",
"Arcaden" and "Einkaufszentrum" are shopping centres, "Klinikum" a hospital,
"Hbf" a station, "P+R" park-and-ride, "Messe" and "Theater" event venues.
Rules are checked in order, so a more specific match wins ("P+R Station"
is park-and-ride, "Universitätsklinikum" a hospital, "Congress Centrum" an
event venue rather than a shopping centre). A standalone "Zentrum" is the
town centre; only compounds ("Main-Taunus-Zentrum") count as shopping.
Names that match nothing -- mostly garages named after a street or square --
are "City centre and other".
Keywords cover German, Dutch, French, Italian and English names.
"""

from __future__ import annotations

import re

TYPES: list[tuple[str, str]] = [
    ("park_ride", r"\bp\s*\+\s*r\b|\bp\s*&\s*r\b|park\s*(?:&|\+|and|\+\s*)\s*ride|\bpr-\d|pendler|relais"),
    ("hospital", r"klinik|krankenhaus|spital(?!str|gasse|platz|tor)|hospital|ospedale|ziekenhuis|h[oô]pital|\bchu\b|medizin|\bmc\b"),
    ("event", r"messe|stadion|stadium|arena|theater|theatre|th[eé][aâ]tre|teatro|oper\b|opera|philharmonie|schauspiel|konzert|"
              r"con?gress|kongress|stadthalle|\bhalle\b|festplatz|\bdult|\bzoo\b|museum|mousonturm|sportpark|eissporthalle|"
              r"palasport|palazzetto|expo|fiera|kultur|concertgebouw|ahoy|jaarbeurs|"
              r"besucherzentrum|ludwig\s*forum|neckar\s*forum"),
    ("station", r"bahnhof|\bhbf\b|\bzob\b|\bstation\b|gare\b|stazione|\bsncf\b|\bbf\b|centraal|\bcs\b|metro"),
    ("university", r"\buni\b|universit|hochschule|campus|fachhochschule|\bfh\b|p[aä]dagogisch|politecnico|ateneo"),
    ("airport", r"flughafen|airport|a[eé]roport|aeroporto|luchthaven|schiphol"),
    ("shopping", r"galerie|galeria|arcaden|passage|einkauf|shopping|\bcenter\b|\w-?zentrum|centre\s+commercial|\bcc\b|kaufhof|karstadt|"
                 r"w[oö]hrl|\bc\s*&\s*a\b|fachmarkt|kaufland|ikea|outlet|\bmall\b|plaza|h[oö]fe\b|forum|carr[eé]e|karree|"
                 r"winkelcentrum|woonmall|\bikea|real\b|globus|famila|marktkauf|leclerc|carrefour|auchan|coop\b|migros|manor|"
                 r"\bkadewe|breuninger|peek|primark|saturn|media\s*markt|\bmtz\b|loop5|alexa\b|centro\b"),
]
OTHER = "city"

LABELS = {
    "park_ride": "Park and ride",
    "hospital": "Hospitals",
    "event": "Event and culture venues",
    "station": "Stations",
    "university": "Universities",
    "airport": "Airports",
    "shopping": "Shopping centres and stores",
    "city": "City centre and other",
}

_COMPILED = [(t, re.compile(p, re.I)) for t, p in TYPES]


def classify(name: str | None) -> str:
    n = (name or "").replace("ß", "ss")
    for t, rx in _COMPILED:
        if rx.search(n):
            return t
    return OTHER
