"""Live parking for Madrid's municipal car parks, via the city's
InfoParking SOAP service (servayto.madrid.es/MTPAR_WSINFO/InfoParking),
listed on datos.madrid.es as dataset 50027 "Aparcamientos públicos
(rotacionales). Datos de ocupación en tiempo real". The first Spanish
source in this project.

GetListParking returns all ~75 municipal car parks with coordinates; about
two dozen also carry an occupation block with free spaces and a timestamp
(with offset). Capacity is only in GetDetailParking ("Número plazas" /
"Total"), one call per car park, so the capacity run makes ~75 spaced
requests weekly. Where a detail has no "Total" its "Normal" count is used.
Those totals agree with the rotational space counts in the city's monthly
occupancy history (dataset 300346) to within a few spaces for most car
parks. That history is monthly averages, not readings, so it is not
imported.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from scrapers.base import CapacityRecord, OccupancyRecord, SourceAdapter

SERVICE_URL = "https://servayto.madrid.es/MTPAR_WSINFO/InfoParking"
SOURCE_WEB_URL = "https://datos.madrid.es/dataset/50027-0-aparcamientosocupacionyservicios"
REQUEST_SPACING_SECONDS = 0.3

_ENVELOPE = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/" '
    'xmlns:ip="http://schemas.datacontract.org/2004/07/InfoParking"><soapenv:Body>{}</soapenv:Body></soapenv:Envelope>'
)
LIST_BODY = _ENVELOPE.format("<tem:GetListParking><tem:language>ES</tem:language></tem:GetListParking>")


def _detail_body(parking_id: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return _ENVELOPE.format(
        "<tem:GetDetailParking><tem:parametersDetailParking>"
        f"<ip:date>{now}</ip:date><ip:family>001</ip:family><ip:id>{parking_id}</ip:id>"
        "<ip:language>ES</ip:language><ip:publicData>true</ip:publicData>"
        "</tem:parametersDetailParking></tem:GetDetailParking>"
    )


def _field(block: str, name: str) -> str | None:
    m = re.search(rf"<ns2:{name}>(.*?)</ns2:{name}>", block, re.S)
    return m.group(1).strip() if m else None


def _soap(fetcher, action: str, body: str) -> str:
    return fetcher.post_text(
        SERVICE_URL,
        body,
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"http://tempuri.org/iInfoParking/{action}"'},
    )


def _parkings(fetcher) -> list[str]:
    return re.findall(r"<ns2:lstParking>(.*?)</ns2:lstParking>", _soap(fetcher, "GetListParking", LIST_BODY), re.S)


class MadridLiveAdapter(SourceAdapter):
    name = "madrid-live"
    fetcher_type = "http"
    occupancy_interval_seconds = 30 * 60
    capacity_interval_seconds = 7 * 24 * 3600

    def fetch_capacity(self, fetcher) -> list[CapacityRecord]:
        records = []
        for p in _parkings(fetcher):
            pid, name = _field(p, "id"), _field(p, "name")
            if not pid or not name:
                continue
            detail = _soap(fetcher, "GetDetailParking", _detail_body(pid))
            time.sleep(REQUEST_SPACING_SECONDS)
            spaces = {
                m.group(2): m.group(1)
                for m in re.finditer(
                    r"<ns2:content>([^<]*)</ns2:content>\s*<ns2:name>([^<]*)</ns2:name>\s*<ns2:nameField>Tipo plaza</ns2:nameField>",
                    detail,
                )
            }
            total = spaces.get("Total") or spaces.get("Normal") or ""
            if not total.isdigit() or int(total) <= 0:
                continue
            lat, lon = _field(p, "latitude"), _field(p, "longitude")
            records.append(
                CapacityRecord(
                    place_id=f"madrid-live-{pid}",
                    place_name=name,
                    city_name="Madrid",
                    num_all=int(total),
                    source_id=self.name,
                    address=_field(p, "address"),
                    latitude=float(lat) if lat else None,
                    longitude=float(lon) if lon else None,
                    source_web_url=SOURCE_WEB_URL,
                )
            )
        return records

    def fetch_occupancy(self, fetcher, known_garages: dict[str, str]) -> list[OccupancyRecord]:
        records = []
        for p in _parkings(fetcher):
            pid = _field(p, "id")
            for occ in re.findall(r"<ns2:occupation>(.*?)</ns2:occupation>", p, re.S):
                free, moment = _field(occ, "free"), _field(occ, "moment")
                if _field(occ, "name") != "Total" or not free or not free.isdigit() or not moment:
                    continue
                ts = datetime.fromisoformat(moment).astimezone(timezone.utc).isoformat(timespec="seconds")
                records.append(OccupancyRecord(place_id=f"madrid-live-{pid}", ts=ts, free=int(free)))
        return records
