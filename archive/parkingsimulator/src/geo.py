import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def garages_within_radius(origin_lat, origin_lon, garages, radius_km):
    out = []
    for g in garages:
        d = haversine_km(origin_lat, origin_lon, g.lat, g.lon)
        if d <= radius_km:
            out.append((g, d))
    return out


def competitor_count(garage, garages, radius_km=0.5):
    return sum(
        1 for g in garages
        if g.id != garage.id and haversine_km(garage.lat, garage.lon, g.lat, g.lon) <= radius_km
    )
