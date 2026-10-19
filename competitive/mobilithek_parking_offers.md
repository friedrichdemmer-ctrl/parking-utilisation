# Mobilithek: parking offers with live or historical occupancy (surveyed 2026-10-19)

Source: the Mobilithek catalogue search (445 offers matched parking terms; 93 mention occupancy, availability or
forecast). "Brokered" offers are DATEX II feeds pulled over HTTPS with a machine certificate (mutual TLS; a request
without one gets `400 No required SSL certificate was sent`). Non-brokered offers are plain downloads. "Approval" means
the data provider must approve each subscription.

Subscription held: Gebündelte Daten Parken NRW (NRW.Mobidrom, DATEX II v2, subscription 1047835186619437056, active,
pull, no limit on retrievals). It bundles live data for Bergkamen, Bielefeld, Düsseldorf, Köln, Krefeld, Wuppertal and
APAG Aachen, plus static APCOA, Contipark and Goldbeck lists.

## München (priority)
| Offer | Provider | Notes |
|---|---|---|
| P+R-Anlagen MVV, dynamisch | MVV | DATEX II v3, brokered, approval required, created 2026-09-11. The licensed source of the feed behind MVV's own P+R map, which `scrapers/adapters/muenchen_mvv_pr.py` reads from the website today |
| P+R-Anlagen MVV, Prognose | MVV | forecast, same terms |
| P+R-Anlagen MVV, statisch / Konfigurationsdaten | MVV | capacity and configuration |
| P+R-Anlagen München, dynamisch / statisch | P+R Park & Ride GmbH | DATEX II, brokered, approval required, since 2021 |
| P+R-Parkplatz Lochhausen Nord: Stellplatzbelegung | ifak e.V. | 10 sensor bays, dl-by-de, no approval; too small to matter |
| P+R-Anlagen Belegungsprognosen (traffic-light), Parkhäuser München, P+R Anlagen München | Landeshauptstadt München | static or forecast only, dl-by-de |

No Mobilithek offer carries live occupancy for Munich's central garages.

## Historical
- Parkhausbelegungen im Verlauf: 2019 bis heute (Münster): 5-minute free counts for the inner-city garages as CSV, updated nightly. Open, not brokered.
- Parkplatzsensoren - Historie (Stadt Dortmund). Open, not brokered.

## Live (brokered DATEX II unless noted)
NRW bundle (held); Köln dynamic; Düsseldorf dynamic; Dortmund Parkleitsystem Innenstadt dynamic; Mönchengladbach Parken Status;
Bremen Parkdaten dynamisch; Augsburg PLS dynamisch; Kassel dynamische Parkdaten; Göttingen PLS; Mainz dynamische Parkdaten;
Magdeburg Parkbelegungsdaten; Erfurt Auslastungsinformationen; Konstanz Parkdaten dynamisch; Oberstdorf PLS; Kiel Altstadt
Belegungsdaten; P+R Hessen (DATEX II v3); Niedersachsen P+R Auslastung (v3); Urban Software Institute Belegungsdaten (v3);
Jena Parkdaten (DATEX II). Not brokered: Münster Parkleitsystem (GeoJSON, once a minute), Nürnberg PLS (Yunex), Freiburg PLS and
P+R, Hamburg Parkhäuser, Heidelberg on-street Auslastung, Herrenberg Park API, Amberg, Gelsenkirchen sensors, Olpe, Scharbeutz.
Out of scope: lorry-parking feeds (Autobahn, Toll Collect SID and similar).
