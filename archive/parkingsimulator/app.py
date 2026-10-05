import hashlib
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.geo import haversine_km

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CITIES_DIR = os.path.join(DATA_DIR, "cities")
DE_DIR = os.path.join(CITIES_DIR, "de")
NL_DIR = os.path.join(CITIES_DIR, "nl")
IE_DIR = os.path.join(CITIES_DIR, "ie")
BE_DIR = os.path.join(CITIES_DIR, "be")
UK_DIR = os.path.join(CITIES_DIR, "uk")
DK_DIR = os.path.join(CITIES_DIR, "dk")
FR_DIR = os.path.join(CITIES_DIR, "fr")

COUNTRIES = {
    "Germany": {
        "Düsseldorf": os.path.join(DATA_DIR, "assets.csv"),
        "Berlin": os.path.join(DE_DIR, "berlin.csv"),
        "Frankfurt": os.path.join(DE_DIR, "frankfurt.csv"),
        "Hamburg": os.path.join(DE_DIR, "hamburg.csv"),
        "Hannover": os.path.join(DE_DIR, "hannover.csv"),
        "Köln": os.path.join(DE_DIR, "koeln.csv"),
        "München": os.path.join(DE_DIR, "muenchen.csv"),
        "Nürnberg": os.path.join(DE_DIR, "nuernberg.csv"),
        "Stuttgart": os.path.join(DE_DIR, "stuttgart.csv"),
        "Bielefeld": os.path.join(DE_DIR, "bielefeld.csv"),
        "Bonn": os.path.join(DE_DIR, "bonn.csv"),
        "Dresden": os.path.join(DE_DIR, "dresden.csv"),
        "Essen": os.path.join(DE_DIR, "essen.csv"),
        "Leipzig": os.path.join(DE_DIR, "leipzig.csv"),
        "Mönchengladbach": os.path.join(DE_DIR, "moenchengladbach.csv"),
        "Wiesbaden": os.path.join(DE_DIR, "wiesbaden.csv"),
        "Wuppertal": os.path.join(DE_DIR, "wuppertal.csv"),
        "Aachen": os.path.join(DE_DIR, "aachen.csv"),
        "Augsburg": os.path.join(DE_DIR, "augsburg.csv"),
        "Darmstadt": os.path.join(DE_DIR, "darmstadt.csv"),
        "Erfurt": os.path.join(DE_DIR, "erfurt.csv"),
        "Heidelberg": os.path.join(DE_DIR, "heidelberg.csv"),
        "Kiel": os.path.join(DE_DIR, "kiel.csv"),
        "Ludwigshafen": os.path.join(DE_DIR, "ludwigshafen.csv"),
        "Saarbrücken": os.path.join(DE_DIR, "saarbruecken.csv"),
        "Fürth": os.path.join(DE_DIR, "fuerth.csv"),
        "Offenbach": os.path.join(DE_DIR, "offenbach.csv"),
        "Leverkusen": os.path.join(DE_DIR, "leverkusen.csv"),
        "Gießen": os.path.join(DE_DIR, "giessen.csv"),
        "Kaiserslautern": os.path.join(DE_DIR, "kaiserslautern.csv"),
        "Rosenheim": os.path.join(DE_DIR, "rosenheim.csv"),
        "Hagen": os.path.join(DE_DIR, "hagen.csv"),
        "Mülheim an der Ruhr": os.path.join(DE_DIR, "muelheim.csv"),
        "Böblingen": os.path.join(DE_DIR, "boeblingen.csv"),
        "Cottbus": os.path.join(DE_DIR, "cottbus.csv"),
        "Fulda": os.path.join(DE_DIR, "fulda.csv"),
        "Landshut": os.path.join(DE_DIR, "landshut.csv"),
        "Lüneburg": os.path.join(DE_DIR, "lueneburg.csv"),
        "Moers": os.path.join(DE_DIR, "moers.csv"),
        "Pforzheim": os.path.join(DE_DIR, "pforzheim.csv"),
        "Rüsselsheim": os.path.join(DE_DIR, "ruesselsheim.csv"),
        "Crimmitschau": os.path.join(DE_DIR, "crimmitschau.csv"),
        "Herne": os.path.join(DE_DIR, "herne.csv"),
        "Hilden": os.path.join(DE_DIR, "hilden.csv"),
        "Lippstadt": os.path.join(DE_DIR, "lippstadt.csv"),
        "Lörrach": os.path.join(DE_DIR, "loerrach.csv"),
        "Northeim": os.path.join(DE_DIR, "northeim.csv"),
        "Remscheid": os.path.join(DE_DIR, "remscheid.csv"),
        "Witten": os.path.join(DE_DIR, "witten.csv"),
    },
    "Netherlands": {
        "Amsterdam": os.path.join(NL_DIR, "amsterdam.csv"),
        "Rotterdam": os.path.join(NL_DIR, "rotterdam.csv"),
        "Den Haag": os.path.join(NL_DIR, "denhaag.csv"),
        "Utrecht": os.path.join(NL_DIR, "utrecht.csv"),
        "Eindhoven": os.path.join(NL_DIR, "eindhoven.csv"),
        "Groningen": os.path.join(NL_DIR, "groningen.csv"),
        "Breda": os.path.join(NL_DIR, "breda.csv"),
        "Nijmegen": os.path.join(NL_DIR, "nijmegen.csv"),
        "Arnhem": os.path.join(NL_DIR, "arnhem.csv"),
        "Maastricht": os.path.join(NL_DIR, "maastricht.csv"),
        "Zwolle": os.path.join(NL_DIR, "zwolle.csv"),
        "Den Bosch": os.path.join(NL_DIR, "denbosch.csv"),
        "Enschede": os.path.join(NL_DIR, "enschede.csv"),
        "Amersfoort": os.path.join(NL_DIR, "amersfoort.csv"),
        "Apeldoorn": os.path.join(NL_DIR, "apeldoorn.csv"),
        "Dordrecht": os.path.join(NL_DIR, "dordrecht.csv"),
        "Alkmaar": os.path.join(NL_DIR, "alkmaar.csv"),
        "Leeuwarden": os.path.join(NL_DIR, "leeuwarden.csv"),
        "Venlo": os.path.join(NL_DIR, "venlo.csv"),
        "Hilversum": os.path.join(NL_DIR, "hilversum.csv"),
        "Ede": os.path.join(NL_DIR, "ede.csv"),
        "Heerlen": os.path.join(NL_DIR, "heerlen.csv"),
        "Helmond": os.path.join(NL_DIR, "helmond.csv"),
        "Hengelo": os.path.join(NL_DIR, "hengelo.csv"),
        "Hoofddorp": os.path.join(NL_DIR, "hoofddorp.csv"),
        "Zaandam": os.path.join(NL_DIR, "zaandam.csv"),
        "Schiedam": os.path.join(NL_DIR, "schiedam.csv"),
        "Vlaardingen": os.path.join(NL_DIR, "vlaardingen.csv"),
        "Roosendaal": os.path.join(NL_DIR, "roosendaal.csv"),
        "Alphen aan den Rijn": os.path.join(NL_DIR, "alphenaandenrijn.csv"),
        "Amstelveen": os.path.join(NL_DIR, "amstelveen.csv"),
        "Assen": os.path.join(NL_DIR, "assen.csv"),
        "Bergen op Zoom": os.path.join(NL_DIR, "bergenopzoom.csv"),
        "Beverwijk": os.path.join(NL_DIR, "beverwijk.csv"),
        "Gouda": os.path.join(NL_DIR, "gouda.csv"),
        "Deventer": os.path.join(NL_DIR, "deventer.csv"),
        "Sittard": os.path.join(NL_DIR, "sittard.csv"),
        "Boxtel": os.path.join(NL_DIR, "boxtel.csv"),
        "Diemen": os.path.join(NL_DIR, "diemen.csv"),
        "Duivendrecht": os.path.join(NL_DIR, "duivendrecht.csv"),
        "Gorinchem": os.path.join(NL_DIR, "gorinchem.csv"),
        "Halfweg": os.path.join(NL_DIR, "halfweg.csv"),
        "Heemstede": os.path.join(NL_DIR, "heemstede.csv"),
        "Heerenveen": os.path.join(NL_DIR, "heerenveen.csv"),
        "Middelburg": os.path.join(NL_DIR, "middelburg.csv"),
        "Driebergen-Rijsenburg": os.path.join(NL_DIR, "driebergenrijsenburg.csv"),
        "Leiderdorp": os.path.join(NL_DIR, "leiderdorp.csv"),
        "Naarden": os.path.join(NL_DIR, "naarden.csv"),
        "Nieuwegein": os.path.join(NL_DIR, "nieuwegein.csv"),
        "Oisterwijk": os.path.join(NL_DIR, "oisterwijk.csv"),
        "Oss": os.path.join(NL_DIR, "oss.csv"),
        "Oud-Beijerland": os.path.join(NL_DIR, "oudbeijerland.csv"),
        "Ridderkerk": os.path.join(NL_DIR, "ridderkerk.csv"),
        "Rijswijk": os.path.join(NL_DIR, "rijswijk.csv"),
        "Roermond": os.path.join(NL_DIR, "roermond.csv"),
        "Sneek": os.path.join(NL_DIR, "sneek.csv"),
        "Valkenburg aan de Geul": os.path.join(NL_DIR, "valkenburg.csv"),
        "Veenendaal": os.path.join(NL_DIR, "veenendaal.csv"),
        "Weert": os.path.join(NL_DIR, "weert.csv"),
        "Woerden": os.path.join(NL_DIR, "woerden.csv"),
        "Zutphen": os.path.join(NL_DIR, "zutphen.csv"),
        "Zwijndrecht": os.path.join(NL_DIR, "zwijndrecht.csv"),
    },
    "Ireland": {
        "Dublin": os.path.join(IE_DIR, "dublin.csv"),
        "Cork": os.path.join(IE_DIR, "cork.csv"),
        "Limerick": os.path.join(IE_DIR, "limerick.csv"),
        "Galway": os.path.join(IE_DIR, "galway.csv"),
        "Bray": os.path.join(IE_DIR, "bray.csv"),
        "Kilkenny": os.path.join(IE_DIR, "kilkenny.csv"),
    },
    "Belgium": {
        "Antwerpen": os.path.join(BE_DIR, "antwerpen.csv"),
        "Brussel": os.path.join(BE_DIR, "brussel.csv"),
        "Hasselt": os.path.join(BE_DIR, "hasselt.csv"),
        "Tongeren-Borgloon": os.path.join(BE_DIR, "tongerenborgloon.csv"),
        "Genk": os.path.join(BE_DIR, "genk.csv"),
        "Leuven": os.path.join(BE_DIR, "leuven.csv"),
        "Mechelen": os.path.join(BE_DIR, "mechelen.csv"),
        "Charleroi": os.path.join(BE_DIR, "charleroi.csv"),
        "Braine-l'Alleud": os.path.join(BE_DIR, "brainelalleud.csv"),
        "Doornik": os.path.join(BE_DIR, "doornik.csv"),
        "Knokke-Heist": os.path.join(BE_DIR, "knokkeheist.csv"),
        "Oostende": os.path.join(BE_DIR, "oostende.csv"),
    },
    "UK": {
        "London": os.path.join(UK_DIR, "london.csv"),
        "Manchester": os.path.join(UK_DIR, "manchester.csv"),
        "Birmingham": os.path.join(UK_DIR, "birmingham.csv"),
        "Sheffield": os.path.join(UK_DIR, "sheffield.csv"),
        "Liverpool": os.path.join(UK_DIR, "liverpool.csv"),
        "Glasgow": os.path.join(UK_DIR, "glasgow.csv"),
        "Leeds": os.path.join(UK_DIR, "leeds.csv"),
        "Edinburgh": os.path.join(UK_DIR, "edinburgh.csv"),
        "Bristol": os.path.join(UK_DIR, "bristol.csv"),
        "Cardiff": os.path.join(UK_DIR, "cardiff.csv"),
        "Nottingham": os.path.join(UK_DIR, "nottingham.csv"),
        "Newcastle-Upon-Tyne": os.path.join(UK_DIR, "newcastleupontyne.csv"),
        "York": os.path.join(UK_DIR, "york.csv"),
        "Belfast": os.path.join(UK_DIR, "belfast.csv"),
        "Colchester": os.path.join(UK_DIR, "colchester.csv"),
        "Bury": os.path.join(UK_DIR, "bury.csv"),
        "Chelmsford": os.path.join(UK_DIR, "chelmsford.csv"),
        "Croydon": os.path.join(UK_DIR, "croydon.csv"),
        "Ealing": os.path.join(UK_DIR, "ealing.csv"),
        "Hemel Hempstead": os.path.join(UK_DIR, "hemelhempstead.csv"),
        "Norwich": os.path.join(UK_DIR, "norwich.csv"),
        "Reading": os.path.join(UK_DIR, "reading.csv"),
        "Romford": os.path.join(UK_DIR, "romford.csv"),
        "Taunton": os.path.join(UK_DIR, "taunton.csv"),
        "Truro": os.path.join(UK_DIR, "truro.csv"),
        "Weymouth": os.path.join(UK_DIR, "weymouth.csv"),
        "Windsor": os.path.join(UK_DIR, "windsor.csv"),
        "Ipswich": os.path.join(UK_DIR, "ipswich.csv"),
        "Gloucester": os.path.join(UK_DIR, "gloucester.csv"),
        "Kingston upon Thames": os.path.join(UK_DIR, "kingstonuponthames.csv"),
    },
    "Denmark": {
        "København": os.path.join(DK_DIR, "koebenhavn.csv"),
        "Aarhus": os.path.join(DK_DIR, "aarhus.csv"),
        "Odense": os.path.join(DK_DIR, "odense.csv"),
        "Frederiksberg": os.path.join(DK_DIR, "frederiksberg.csv"),
        "Randers": os.path.join(DK_DIR, "randers.csv"),
        "Aalborg": os.path.join(DK_DIR, "aalborg.csv"),
        "Helsingør": os.path.join(DK_DIR, "helsingoer.csv"),
        "Hillerød": os.path.join(DK_DIR, "hillerod.csv"),
        "Kolding": os.path.join(DK_DIR, "kolding.csv"),
        "Lyngby": os.path.join(DK_DIR, "lyngby.csv"),
        "Silkeborg": os.path.join(DK_DIR, "silkeborg.csv"),
        "Slagelse": os.path.join(DK_DIR, "slagelse.csv"),
        "Svendborg": os.path.join(DK_DIR, "svendborg.csv"),
        "Risskov": os.path.join(DK_DIR, "risskov.csv"),
        "Skanderborg": os.path.join(DK_DIR, "skanderborg.csv"),
        "Horsens": os.path.join(DK_DIR, "horsens.csv"),
        "Søborg": os.path.join(DK_DIR, "soeborg.csv"),
        "Taastrup": os.path.join(DK_DIR, "taastrup.csv"),
        "Vejle": os.path.join(DK_DIR, "vejle.csv"),
        "Albertslund": os.path.join(DK_DIR, "albertslund.csv"),
        "Ballerup": os.path.join(DK_DIR, "ballerup.csv"),
        "Fredericia": os.path.join(DK_DIR, "fredericia.csv"),
        "Ringsted": os.path.join(DK_DIR, "ringsted.csv"),
        "Valby": os.path.join(DK_DIR, "valby.csv"),
        "Bagsværd": os.path.join(DK_DIR, "bagsvaerd.csv"),
        "Brønshøj": os.path.join(DK_DIR, "broenshoej.csv"),
        "Frederikshavn": os.path.join(DK_DIR, "frederikshavn.csv"),
        "Hellerup": os.path.join(DK_DIR, "hellerup.csv"),
        "Herlev": os.path.join(DK_DIR, "herlev.csv"),
        "Hjørring": os.path.join(DK_DIR, "hjoerring.csv"),
        "Aabyhøj": os.path.join(DK_DIR, "aabyhoej.csv"),
        "Birkerød": os.path.join(DK_DIR, "birkeroed.csv"),
        "Blokhus": os.path.join(DK_DIR, "blokhus.csv"),
        "Brabrand": os.path.join(DK_DIR, "brabrand.csv"),
        "Ebeltoft": os.path.join(DK_DIR, "ebeltoft.csv"),
        "Esbjerg": os.path.join(DK_DIR, "esbjerg.csv"),
        "Frederikssund": os.path.join(DK_DIR, "frederikssund.csv"),
        "Gentofte": os.path.join(DK_DIR, "gentofte.csv"),
        "Glostrup": os.path.join(DK_DIR, "glostrup.csv"),
        "Grenaa": os.path.join(DK_DIR, "grenaa.csv"),
        "Greve Strand": os.path.join(DK_DIR, "grevestrand.csv"),
        "Hadsund": os.path.join(DK_DIR, "hadsund.csv"),
        "Holbæk": os.path.join(DK_DIR, "holbaek.csv"),
        "Holme-Olstrup": os.path.join(DK_DIR, "holmeolstrup.csv"),
        "Holstebro": os.path.join(DK_DIR, "holstebro.csv"),
        "Kalundborg": os.path.join(DK_DIR, "kalundborg.csv"),
        "Karrebæksminde": os.path.join(DK_DIR, "karrebaeksminde.csv"),
        "Kastrup": os.path.join(DK_DIR, "kastrup.csv"),
        "Køge": os.path.join(DK_DIR, "koege.csv"),
        "Korsør": os.path.join(DK_DIR, "korsoer.csv"),
        "Middelfart": os.path.join(DK_DIR, "middelfart.csv"),
        "Nørre-Alslev": os.path.join(DK_DIR, "noerrealslev.csv"),
        "Nykøbing F": os.path.join(DK_DIR, "nykoebingf.csv"),
        "Padborg": os.path.join(DK_DIR, "padborg.csv"),
        "Ringe": os.path.join(DK_DIR, "ringe.csv"),
        "Roskilde": os.path.join(DK_DIR, "roskilde.csv"),
        "Sjællands Odde": os.path.join(DK_DIR, "sjaellandsodde.csv"),
        "Skagen": os.path.join(DK_DIR, "skagen.csv"),
        "Skive": os.path.join(DK_DIR, "skive.csv"),
        "Slangerup": os.path.join(DK_DIR, "slangerup.csv"),
        "Stege": os.path.join(DK_DIR, "stege.csv"),
        "Thisted": os.path.join(DK_DIR, "thisted.csv"),
        "Tønder": os.path.join(DK_DIR, "toender.csv"),
        "Vallensbæk": os.path.join(DK_DIR, "vallensbaek.csv"),
        "Vanløse": os.path.join(DK_DIR, "vanloese.csv"),
        "Viborg": os.path.join(DK_DIR, "viborg.csv"),
        "Viby J": os.path.join(DK_DIR, "vibyj.csv"),
    },
    "France": {
        "Paris": os.path.join(FR_DIR, "paris.csv"),
        "Marseille": os.path.join(FR_DIR, "marseille.csv"),
        "Chambéry": os.path.join(FR_DIR, "chambery.csv"),
        "Courbevoie": os.path.join(FR_DIR, "courbevoie.csv"),
        "Bourg Saint Maurice Les Arcs": os.path.join(FR_DIR, "bourgsaintmauricelesarcs.csv"),
        "Toulon": os.path.join(FR_DIR, "toulon.csv"),
        "Paris La Défense": os.path.join(FR_DIR, "parisladefense.csv"),
        "Val d'Isère": os.path.join(FR_DIR, "valdisere.csv"),
        "Valence": os.path.join(FR_DIR, "valence.csv"),
        "Boulogne sur Mer": os.path.join(FR_DIR, "boulognesurmer.csv"),
        "Clermont Ferrand": os.path.join(FR_DIR, "clermontferrand.csv"),
        "Metz": os.path.join(FR_DIR, "metz.csv"),
        "Annemasse": os.path.join(FR_DIR, "annemasse.csv"),
        "Colombes": os.path.join(FR_DIR, "colombes.csv"),
        "Epinal": os.path.join(FR_DIR, "epinal.csv"),
        "La Plagne": os.path.join(FR_DIR, "laplagne.csv"),
        "Antibes": os.path.join(FR_DIR, "antibes.csv"),
        "Aubagne": os.path.join(FR_DIR, "aubagne.csv"),
        "Bergerac": os.path.join(FR_DIR, "bergerac.csv"),
        "Chartres": os.path.join(FR_DIR, "chartres.csv"),
        "Evian Les Bains": os.path.join(FR_DIR, "evianlesbains.csv"),
        "Chalon sur Saône": os.path.join(FR_DIR, "chalonsursaone.csv"),
        "Lyon": os.path.join(FR_DIR, "lyon.csv"),
        "Montauban": os.path.join(FR_DIR, "montauban.csv"),
        "Castres": os.path.join(FR_DIR, "castres.csv"),
        "Houdan": os.path.join(FR_DIR, "houdan.csv"),
        "Mâcon": os.path.join(FR_DIR, "macon.csv"),
        "Nancy": os.path.join(FR_DIR, "nancy.csv"),
        "Saint Etienne": os.path.join(FR_DIR, "saintetienne.csv"),
        "Toulouse": os.path.join(FR_DIR, "toulouse.csv"),
        "Albi": os.path.join(FR_DIR, "albi.csv"),
        "Annecy": os.path.join(FR_DIR, "annecy.csv"),
        "Arcueil": os.path.join(FR_DIR, "arcueil.csv"),
        "Belley": os.path.join(FR_DIR, "belley.csv"),
        "Béthune": os.path.join(FR_DIR, "bethune.csv"),
        "Bonneville": os.path.join(FR_DIR, "bonneville.csv"),
        "Bordeaux": os.path.join(FR_DIR, "bordeaux.csv"),
        "Boulogne Billancourt": os.path.join(FR_DIR, "boulognebillancourt.csv"),
        "Bourgoin-Jallieu": os.path.join(FR_DIR, "bourgoinjallieu.csv"),
        "Brest": os.path.join(FR_DIR, "brest.csv"),
        "Corbeil Essonnes": os.path.join(FR_DIR, "corbeilessonnes.csv"),
        "Dijon": os.path.join(FR_DIR, "dijon.csv"),
        "Evreux": os.path.join(FR_DIR, "evreux.csv"),
        "Gex": os.path.join(FR_DIR, "gex.csv"),
        "Gonesse": os.path.join(FR_DIR, "gonesse.csv"),
        "Grenoble": os.path.join(FR_DIR, "grenoble.csv"),
        "Issy Les Moulineaux": os.path.join(FR_DIR, "issylesmoulineaux.csv"),
        "La Ciotat": os.path.join(FR_DIR, "laciotat.csv"),
        "Lagny sur Marne": os.path.join(FR_DIR, "lagnysurmarne.csv"),
        "Le Plessis Robinson": os.path.join(FR_DIR, "leplessisrobinson.csv"),
        "Longvic": os.path.join(FR_DIR, "longvic.csv"),
        "Montigny le Bretonneux": os.path.join(FR_DIR, "montignylebretonneux.csv"),
        "Neuilly sur Seine": os.path.join(FR_DIR, "neuillysurseine.csv"),
        "Nice": os.path.join(FR_DIR, "nice.csv"),
        "Nîmes": os.path.join(FR_DIR, "nimes.csv"),
        "Perpignan": os.path.join(FR_DIR, "perpignan.csv"),
        "Pierre Benite": os.path.join(FR_DIR, "pierrebenite.csv"),
        "Poitiers": os.path.join(FR_DIR, "poitiers.csv"),
        "Reims": os.path.join(FR_DIR, "reims.csv"),
        "Rouen": os.path.join(FR_DIR, "rouen.csv"),
        "Saint Brieuc": os.path.join(FR_DIR, "saintbrieuc.csv"),
        "Saintes": os.path.join(FR_DIR, "saintes.csv"),
        "Saint Germain en Laye": os.path.join(FR_DIR, "saintgermainenlaye.csv"),
        "Saint Julien les Metz": os.path.join(FR_DIR, "saintjulienlesmetz.csv"),
        "Saint Laurent du Var": os.path.join(FR_DIR, "saintlaurentduvar.csv"),
        "Saint Malo": os.path.join(FR_DIR, "saintmalo.csv"),
        "Saint Mandé": os.path.join(FR_DIR, "saintmande.csv"),
        "Saint Quentin": os.path.join(FR_DIR, "saintquentin.csv"),
        "Sartrouville": os.path.join(FR_DIR, "sartrouville.csv"),
        "Uzès": os.path.join(FR_DIR, "uzes.csv"),
        "Vannes": os.path.join(FR_DIR, "vannes.csv"),
        "Vélizy-Villacoublay": os.path.join(FR_DIR, "velizyvillacoublay.csv"),
        "Vichy": os.path.join(FR_DIR, "vichy.csv"),
        "Villaroger": os.path.join(FR_DIR, "villaroger.csv"),
        "Villeurbanne": os.path.join(FR_DIR, "villeurbanne.csv"),
        "Viroflay": os.path.join(FR_DIR, "viroflay.csv"),
    },
}

NEIGHBOR_RADIUS_KM = 0.5

BASE_OPERATOR_COLORS = {
    "Q-Park": "#3366CC",
    "APCOA": "#8FB8F0",
    "Contipark": "#E0574A",
    "B+B Parkhaus": "#F2A7A0",
}
FALLBACK_PALETTE = [
    "#2CA02C", "#9467BD", "#8C564B", "#17BECF", "#BCBD22", "#FF7F0E", "#E377C2",
    "#1A9850", "#6A3D9A", "#B15928", "#A6CEE3", "#FDBF6F",
    "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854", "#FFD92F",
    "#7FC97F", "#BEAED4", "#FDC086", "#386CB0", "#F0027F", "#BF5B17",
]
UNSELECTED_COLOR = "#6E6E6E"

NEUTRAL_BAND_PCT = 5.0   # +/- this % vs the 500m-neighbour average reads as grey ("no real difference")
FULL_COLOR_PCT = 15.0    # by +/- this %, colour is already fully saturated red/green — not stretched
                          # out to whatever the most extreme garage in view happens to be, so a
                          # garage doesn't look washed-out grey just because one outlier exists elsewhere.

PERF_RED = (176, 42, 42)      # #B02A2A
PERF_GREY = (181, 181, 181)   # #B5B5B5
PERF_GREEN = (34, 139, 79)    # #228B4F


def _stable_palette_index(name, n):
    """Deterministic across runs/processes (unlike Python's built-in hash(), which is
    randomized per-process) so the same operator name always lands on the same colour,
    regardless of which city's operator list it's being assigned within."""
    return int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % n


def operator_color_map(operators):
    """Assigns each operator its hash-stable colour so the same name looks the same across
    cities, but resolves any same-city collision (two different fallback-palette operators
    hashing to the same slot) by probing to the next free slot, so no two operators shown
    together on one map ever share a colour."""
    colors = {}
    used_indices = set()
    n = len(FALLBACK_PALETTE)
    fallback_ops = [op for op in operators if op not in BASE_OPERATOR_COLORS]
    for op in operators:
        if op in BASE_OPERATOR_COLORS:
            colors[op] = BASE_OPERATOR_COLORS[op]
    for op in sorted(fallback_ops):
        idx = _stable_palette_index(op, n)
        offset = 0
        while idx in used_indices and offset < n:
            offset += 1
            idx = (idx + 1) % n
        used_indices.add(idx)
        colors[op] = FALLBACK_PALETTE[idx]
    return colors


def _lerp_rgb(c1, c2, t):
    return tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _rgb_to_hex(rgb):
    return "#%02X%02X%02X" % rgb


def value_to_hex(v, band_pct=NEUTRAL_BAND_PCT, full_pct=FULL_COLOR_PCT):
    """Grey within +/- band_pct, solid red/green beyond +/- full_pct, smooth gradient
    between the two. Fixed thresholds (not scaled to the current dataset's extremes),
    so a garage 11% above its neighbours always reads as clearly green."""
    if -band_pct <= v <= band_pct:
        return _rgb_to_hex(PERF_GREY)
    if v <= -full_pct:
        return _rgb_to_hex(PERF_RED)
    if v >= full_pct:
        return _rgb_to_hex(PERF_GREEN)
    if v < 0:
        t = (-v - band_pct) / (full_pct - band_pct)
        return _rgb_to_hex(_lerp_rgb(PERF_GREY, PERF_RED, t))
    t = (v - band_pct) / (full_pct - band_pct)
    return _rgb_to_hex(_lerp_rgb(PERF_GREY, PERF_GREEN, t))


def build_performance_colorscale(max_abs_pct, band_pct=NEUTRAL_BAND_PCT, full_pct=FULL_COLOR_PCT):
    """Colorbar legend matching value_to_hex exactly. Used only for the SVG colorbar —
    Plotly's Scattermapbox marker layer mis-renders unevenly-spaced continuous
    colorscales on WebGL, so the actual markers are coloured manually via value_to_hex."""
    max_abs_pct = max(max_abs_pct, full_pct)
    band_edge = band_pct / (2 * max_abs_pct)
    full_edge = full_pct / (2 * max_abs_pct)
    lo_band, hi_band = 0.5 - band_edge, 0.5 + band_edge
    lo_full, hi_full = 0.5 - full_edge, 0.5 + full_edge
    stops = [[0.0, _rgb_to_hex(PERF_RED)]]
    if lo_full > 1e-6:
        stops.append([lo_full, _rgb_to_hex(PERF_RED)])
    stops += [[lo_band, _rgb_to_hex(PERF_GREY)], [hi_band, _rgb_to_hex(PERF_GREY)]]
    if hi_full < 1 - 1e-6:
        stops.append([hi_full, _rgb_to_hex(PERF_GREEN)])
    stops.append([1.0, _rgb_to_hex(PERF_GREEN)])
    return stops


st.set_page_config(page_title="Parking Competitive Analysis", layout="wide")


@st.cache_data
def load_garages(csv_path):
    df = pd.read_csv(csv_path)
    df["capacity"] = pd.to_numeric(df["capacity"], errors="coerce")
    df["hourly_rate"] = pd.to_numeric(df["hourly_rate"], errors="coerce")
    if "daily_cap" in df.columns:
        df["daily_cap"] = pd.to_numeric(df["daily_cap"], errors="coerce")
    return df


def bubble_sizes(capacities, min_px=7, max_px=34):
    cmin, cmax = capacities.min(), capacities.max()
    mid = (min_px + max_px) / 2
    if pd.isna(cmin) or pd.isna(cmax) or cmax == cmin:
        return pd.Series([mid] * len(capacities), index=capacities.index)
    return (min_px + (capacities - cmin) / (cmax - cmin) * (max_px - min_px)).fillna(mid)


def neighbors_within_radius(garage_row, all_garages, radius_km):
    others = all_garages[all_garages["id"] != garage_row["id"]]
    dists = others.apply(
        lambda r: haversine_km(garage_row["lat"], garage_row["lon"], r["lat"], r["lon"]), axis=1
    )
    return others[dists <= radius_km]


def format_capacity(v):
    return f"{int(v)} spaces" if pd.notna(v) else "capacity n/a"


def format_price(v, currency="€"):
    if pd.isna(v):
        return "price n/a"
    if currency.endswith("."):
        return f"{v:.2f} {currency}/h"
    return f"{currency}{v:.2f}/h"


COUNTRY_CURRENCY = {
    "Germany": "€",
    "Netherlands": "€",
    "Ireland": "€",
    "Belgium": "€",
    "UK": "£",
    "Denmark": "kr.",
    "France": "€",
}


st.title("Parking Competitive Analysis")

country_col, city_col = st.columns(2)
with country_col:
    country = st.selectbox("Country", list(COUNTRIES.keys()), index=0)
cities_in_country = COUNTRIES[country]
if not cities_in_country:
    st.info(f"No cities researched yet for {country}.")
    st.stop()
with city_col:
    city = st.selectbox("City", list(cities_in_country.keys()), index=0)
currency_symbol = COUNTRY_CURRENCY.get(country, "€")
garages_df = load_garages(cities_in_country[city])
garages_df["_size"] = bubble_sizes(garages_df["capacity"])

total_capacity = garages_df["capacity"].sum()
n_operators = garages_df["operator"].nunique()
n_priced = garages_df["hourly_rate"].notna().sum()
st.caption(
    f"{len(garages_df)} garages · {n_operators} operators · {int(total_capacity):,} spaces "
    f"(where published) · {n_priced}/{len(garages_df)} with published hourly pricing"
)
st.caption(
    "Names, addresses, capacities, and hourly/daily pricing are real, sourced from each operator's own "
    "site or live pricing API and geocoded via OpenStreetMap/embedded page coordinates. Where an operator "
    "doesn't publish a rate for a garage, price is left blank rather than estimated."
)

color_mode = st.radio(
    "Colour mode",
    ["By operator", "Relative performance vs. nearby garages (500m)"],
    horizontal=True,
)

fig_map = go.Figure()

if color_mode == "By operator":
    operator_options = sorted(garages_df["operator"].unique())
    operator_colors = operator_color_map(operator_options)
    selected_operators = st.multiselect("Highlight operators", operator_options, default=operator_options)

    background = garages_df[~garages_df["operator"].isin(selected_operators)]
    if len(background):
        fig_map.add_trace(go.Scattermap(
            lat=background["lat"], lon=background["lon"],
            mode="markers",
            marker=dict(size=background["_size"], color=UNSELECTED_COLOR, opacity=0.8),
            text=(
                background["name"] + " (" + background["operator"] + ") — "
                + background["capacity"].map(format_capacity)
            ),
            hoverinfo="text",
            name="Not highlighted",
            showlegend=False,
        ))

    for op in selected_operators:
        sub = garages_df[garages_df["operator"] == op]
        fig_map.add_trace(go.Scattermap(
            lat=sub["lat"], lon=sub["lon"],
            mode="markers",
            marker=dict(size=sub["_size"], color=operator_colors.get(op, "#888888"), opacity=0.9),
            text=(
                sub["name"] + " (" + sub["operator"] + ") — " + sub["capacity"].map(format_capacity)
                + " · " + sub["hourly_rate"].map(lambda v: format_price(v, currency_symbol))
            ),
            hoverinfo="text",
            name=op,
        ))

    shown_df = garages_df[garages_df["operator"].isin(selected_operators)]
    map_col1, map_col2, map_col3 = st.columns(3)
    map_col1.metric("Garages highlighted", len(shown_df))
    map_col2.metric("Spaces highlighted", f"{int(shown_df['capacity'].sum()):,}")
    map_col3.metric("Operators highlighted", len(selected_operators))

else:
    # (column, invert): invert=True means LOWER raw values are better (e.g. distance to
    # city centre), so the sign is flipped before colouring — green always means "better".
    metric_options = {
        f"Price ({currency_symbol}/hour)": ("hourly_rate", False),
        "Location quality (proximity to city centre)": ("_distance_km", True),
    }
    pf_col1, pf_col2 = st.columns([1, 2])
    with pf_col1:
        single_operator = st.selectbox("Operator to analyse", sorted(garages_df["operator"].unique()))
    with pf_col2:
        metric_label = st.selectbox("Metric — coloured vs. average of garages within 500m", list(metric_options.keys()))
    metric_col, metric_invert = metric_options[metric_label]

    def format_metric_value(v, col=metric_col):
        if pd.isna(v):
            return "price n/a" if col == "hourly_rate" else "n/a"
        if col == "hourly_rate":
            return format_price(v, currency_symbol)
        if col == "_distance_km":
            return f"{v:.2f} km from centre"
        return str(v)

    work_df = garages_df.copy()
    city_center = (work_df["lat"].mean(), work_df["lon"].mean())
    work_df["_distance_km"] = work_df.apply(
        lambda r: haversine_km(r["lat"], r["lon"], city_center[0], city_center[1]), axis=1
    )

    target = work_df[work_df["operator"] == single_operator].copy()
    deltas, neighbor_counts = [], []
    for _, g in target.iterrows():
        nb = neighbors_within_radius(g, work_df, NEIGHBOR_RADIUS_KM)
        neighbor_counts.append(len(nb))
        own_value = g[metric_col]
        neighbor_avg = nb[metric_col].mean() if len(nb) else None
        if pd.isna(own_value) or not neighbor_avg or pd.isna(neighbor_avg):
            deltas.append(None)
        else:
            pct = (own_value - neighbor_avg) / neighbor_avg * 100
            deltas.append(round(-pct if metric_invert else pct, 1))
    target["_delta"] = deltas
    target["_neighbor_count"] = neighbor_counts

    background = work_df[work_df["operator"] != single_operator]
    fig_map.add_trace(go.Scattermap(
        lat=background["lat"], lon=background["lon"],
        mode="markers",
        marker=dict(size=background["_size"], color=UNSELECTED_COLOR, opacity=0.8),
        text=(
            background["name"] + " (" + background["operator"] + ")<br>"
            + background[metric_col].map(format_metric_value)
        ),
        hoverinfo="text",
        showlegend=False,
    ))

    no_data = target[target["_delta"].isna()]
    has_data = target[target["_delta"].notna()]

    if len(no_data):
        fig_map.add_trace(go.Scattermap(
            lat=no_data["lat"], lon=no_data["lon"],
            mode="markers",
            marker=dict(size=no_data["_size"], color="#F5A623", opacity=0.9),
            text=(
                no_data["name"] + " (" + no_data["operator"] + ")<br>"
                + no_data[metric_col].map(format_metric_value)
                + "<br>No comparable data within 500m"
            ),
            hoverinfo="text",
            name=f"{single_operator} (no comparison data)",
        ))

    if len(has_data):
        max_abs = max(abs(has_data["_delta"].min()), abs(has_data["_delta"].max())) or FULL_COLOR_PCT
        marker_colors = has_data["_delta"].map(value_to_hex).tolist()

        # Scattermapbox on WebGL mis-renders continuous marker colouring for
        # unevenly-spaced custom colorscales, so colours are precomputed per-point
        # above (value_to_hex) and passed as literal hex strings here. This dummy,
        # invisible trace exists purely to draw a matching colorbar legend.
        fig_map.add_trace(go.Scattermap(
            lat=[has_data["lat"].iloc[0]], lon=[has_data["lon"].iloc[0]],
            mode="markers",
            marker=dict(
                size=0.01,
                color=[0],
                colorscale=build_performance_colorscale(max_abs),
                cmin=-max_abs,
                cmax=max_abs,
                showscale=True,
                colorbar=dict(
                    title=dict(text=metric_label + "<br>% vs 500m avg", side="right"),
                    ticksuffix="%",
                ),
                opacity=0,
            ),
            hoverinfo="skip",
            showlegend=False,
        ))

        fig_map.add_trace(go.Scattermap(
            lat=has_data["lat"], lon=has_data["lon"],
            mode="markers",
            marker=dict(size=has_data["_size"], color=marker_colors, opacity=0.95),
            text=(
                has_data["name"] + " (" + has_data["operator"] + ")<br>"
                + has_data[metric_col].map(format_metric_value)
                + "<br>" + metric_label + " vs neighbours: "
                + has_data["_delta"].map(lambda v: f"{v:+.1f}%")
                + "<br>Neighbours within 500m: " + has_data["_neighbor_count"].astype(str)
            ),
            hoverinfo="text",
            name=f"{single_operator} (relative performance)",
        ))

    price_note = (
        " For price, green just means \"priced above the local average\" — that isn't automatically "
        "good or bad for the business, judge it in context." if metric_col == "hourly_rate" else ""
    )
    st.caption(
        f"All garages are always shown. Grey = every operator except {single_operator}. "
        f"{single_operator}'s own garages are coloured by % difference from the average of all other "
        f"garages within 500m: grey = within ±{NEUTRAL_BAND_PCT:.0f}% (no real difference), "
        "green = more than that above average, red = more than that below. Amber = no published data "
        "for this garage or no comparable garage within 500m." + price_note + " \"Location quality\" "
        "compares distance to this city's garage-density centroid (closer = green), a proxy rather than "
        "a published metric."
    )

fig_map.update_layout(
    map_style="open-street-map",
    map=dict(center=dict(lat=garages_df["lat"].mean(), lon=garages_df["lon"].mean()), zoom=11.5),
    height=560,
    margin={"r": 0, "t": 0, "l": 0, "b": 0},
    legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
)
st.plotly_chart(fig_map, use_container_width=True)

st.divider()
st.subheader(f"All garages — {city}")
display_cols = ["id", "name", "operator", "capacity", "hourly_rate", "daily_cap", "has_ev", "address"]
display_cols = [c for c in display_cols if c in garages_df.columns]
st.dataframe(garages_df[display_cols], use_container_width=True, hide_index=True)
