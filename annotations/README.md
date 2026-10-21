# Annotations

`events.csv` is the hand-kept list of dated events that the trends page marks on its charts.

- One row per event; `start`/`end` are `YYYY-MM` or `YYYY-MM-DD` (end blank = still in force).
- `scope`: `DE`, `EU`, `all`. The overall index is ~95% German capacity until 2026 (see the
  composition note on /trends), so German events are the ones that can explain it.
- `kind`: health, transport, fuel, economy, structural, data.
- `measure=yes`: `trends_report.py` also computes the step in the seasonally adjusted index
  over the three months after the start against the three before, and says whether it is
  distinguishable from normal month-to-month movement. `no` for gradual events (a recovery
  that follows a lockdown is not a "step at the start").
- Every row carries a source and a `confidence`. Say what a source says; never attribute a
  movement to an event on the strength of timing alone.
- Review the list when the trends report is rebuilt each quarter and add new policy changes.

## City context (`cities/`)

Per-city notes shown in the city briefing on Explore (city_briefing.py, /api/briefing).

1. A researcher writes `<country>_<city>.draft.json`: dated items with topic, source URL/title and a
   confidence, from sources it actually opened (never from memory).
2. A SEPARATE fact-check re-opens every source and writes `<country>_<city>.verdict.json`
   (supported / partly / unsupported / unreachable, with corrected text, title, date).
3. `python3 annotations/cities/build.py` writes the published `<country>_<city>.json`: supported items
   as written, "partly" items with the checker's corrected text, everything else dropped. A draft
   without a verdict file is never published.

Drafts and verdicts stay in the repo as the audit trail but are kept out of the Docker image.
Proposals, plans and forecasts must stay worded as such; never state a price as in force unless the
source says it is. Refresh each quarter. Researched and written 2026-10-06 to 2026-10-21 (151 cities): Düsseldorf, Dresden, Bielefeld, Osnabrück, Frankfurt,
Amsterdam, Hamburg, Nürnberg, Lyon, Heidelberg, Zürich, Basel, Bordeaux, Mannheim, Münster, Torino,
Nantes, Strasbourg, Dortmund, Freiburg, Karlsruhe, Heilbronn, Madrid, Marseille, Salzburg, Luxembourg, Bolzano, Jena, Bochum, Bonn, Lille, Vigo, Firenze, Helsinki, Gent, Regensburg, Kassel, Augsburg, Leipzig, Ulm, Wiesbaden, Trier, Potsdam, Málaga, Newcastle upon Tyne, La Rochelle, Lübeck, St. Gallen, Ingolstadt, Oldenburg, Den Haag, Utrecht, Rotterdam, München, Braunschweig, Bad Homburg, Gateshead, Espoo, Aalen, Aachen, Köln, Bietigheim-Bissingen, Moers, Grenoble, Rennes, Montpellier, Val Gardena, Merano, Durham, Angers, Orléans, Nîmes, Poitiers, Reims, Clermont-Ferrand, Brest, Hannover, Gießen, Bologna, Brunico, Bressanone, Arnhem, Frauenfeld, then on 2026-10-21: Vantaa, Tampere, Eindhoven, Groningen, Nijmegen, Maastricht, Amersfoort, Breda, Deventer, Roosendaal, Vejle, North Tyneside, Sunderland, South Tyneside, Caldaro, Castelrotto, Caen, Cesson-Sévigné, Mérignac, Pessac, Bruges (Gironde), Floirac, Bassens, Cassis, La Ciotat, Wunstorf, Herrenberg, Le Mans, Quakenbrück, Bad Rothenfelde, Dülmen, Zutphen, Weert, Veenendaal, Sittard, Hengelo, Oss, Heerlen, Roermond, Leeuwarden, Villenave-d'Ornon, Talence, Bègles, Lormont, Le Haillan, Castelnau-le-Lez, Saint-Jean-de-Braye, Olivet, Racines, Curon Venosta, Senales, Konstanz, Pamplona, Mainz, Tourcoing, Apeldoorn, Assen, Bergen op Zoom, Boxtel, Dordrecht, Enschede, Gorinchem, Heerenveen, Middelburg, Oisterwijk, Sneek, Woerden, Zwolle.
Candidates next: the Mobilithek cities once their access is approved (München, Düsseldorf, Augsburg, Göttingen, Mönchengladbach, Oberstdorf), then the remaining small park-and-ride places. Before quoting occupancy for a lot, check that its feed has more than a couple of distinct free values (Veenendaal's Duivenweide and Gemeentehuis feeds and most of München's MVV sensors are stuck); peak-hour labels in the measurement database are UTC, so convert to local time (+1 or +2 hours) before writing 'morning' or 'evening'.
Sources a page itself labels as AI-written are not cited (Torino's via Roma item).


### Unconfirmed claims and unreadable sources (rule set by the owner, 2026-10-06)

- Never invent or round up a claim. If a source cannot be opened or read in full, the claim is NOT
  presented as fact: the fact-check marks it `unreachable`, and `build.py` publishes it only as an
  "unconfirmed" item (shown under "Reported, but not confirmed" with the reason and the link), worded as
  what a search result says. Narrative text never cites an unconfirmed item.
- Items the checker could read only in part (paywall, login, registration wall) are published with the
  note "only the headline and opening could be read".
- Where a PDF is unreadable, give the owner the link; the owner investigates and uploads the document to
  `annotations/cities/uploads/` (see the README there). Then re-check the item against the upload.
- Verifier prompts must say: do not accept a search snippet as confirmation; mark the item unreachable;
  give `unconfirmed_text` and `unconfirmed_reason` for it.


Verdict files must have exactly one entry per draft item, `index` = draft position. Two verdicts (Heidelberg, Nîmes) skipped one item and shifted all later ones, publishing wrong text; check with a script after every fact-check.
