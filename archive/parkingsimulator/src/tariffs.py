def scenario_hourly_rate(garage, overlay):
    rate = garage.tariff.hourly_rate * overlay.price_multiplier
    rate *= overlay.zone_price_multiplier.get(garage.zone, 1.0)
    cap = overlay.price_cap_by_zone.get(garage.zone)
    if cap is not None:
        rate = min(rate, cap)
    return round(rate, 2)


def effective_price(hourly_rate, daily_cap, duration_hours, member_discount_pct=0.0, is_member=False):
    price = hourly_rate * duration_hours
    if daily_cap is not None:
        price = min(price, daily_cap)
    if is_member and member_discount_pct:
        price *= (1 - member_discount_pct)
    return round(price, 2)
