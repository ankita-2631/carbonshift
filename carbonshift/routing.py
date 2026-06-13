"""Route + charging-infrastructure analysis for fleet electrification.

Given a vehicle's daily route, the candidate EV's range, whether it can charge at
the depot overnight, and the rapid chargers known along the route, this decides
whether an EV can realistically serve the route.

Charger counts come from live OpenStreetMap data via the Overpass API
(https://overpass-api.de/) when the route's coordinates are supplied — this is fully
key-free open data (ODbL). When the coordinates are absent or the service is
unreachable, a static fallback figure on the vehicle is used instead.

It is deliberately honest: if the route is longer than the EV can cover and there is
nowhere to recharge en route, the agent keeps the combustion vehicle rather than
stranding the driver — and flags that deploying a charger would unlock the switch.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache

import requests

# Extra minutes per day for a single rapid charge taken on the route.
RAPID_CHARGE_MIN = 35.0
# Usable fraction of nameplate range, allowing for winter/load/derating. Conservative.
USABLE_RANGE_FRAC = 0.85

# OpenStreetMap Overpass API — key-free public EV charging-station data.
# Several public mirrors; we try them in order so a rate-limited primary falls back
# to a mirror rather than dropping to the static estimate.
OVERPASS_ENDPOINTS = [
    e.strip()
    for e in os.environ.get(
        "OVERPASS_API",
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter",
    ).split(",")
    if e.strip()
]


@lru_cache(maxsize=128)
def live_chargers_near(lat: float, lon: float, radius_km: float) -> int | None:
    """Real count of public EV charging stations near a route centre (OpenStreetMap).

    Queries the Overpass API for ``amenity=charging_station`` features within
    ``radius_km`` of the point, trying each configured mirror until one responds.
    Returns the count, or ``None`` if every endpoint is unavailable (the caller then
    falls back to the static estimate). Results are cached per (lat, lon, radius).
    """
    radius_m = int(radius_km * 1000)
    query = (
        f"[out:json][timeout:25];"
        f"(node(around:{radius_m},{lat},{lon})[amenity=charging_station];"
        f"way(around:{radius_m},{lat},{lon})[amenity=charging_station];);"
        f"out count;"
    )
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(
                endpoint,
                data=query,
                headers={"Accept": "application/json", "User-Agent": "CarbonShift/1.0"},
                timeout=30,
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            if elements and "tags" in elements[0]:
                return int(elements[0]["tags"].get("total", 0))
            return 0
        except Exception:
            continue  # try the next mirror
    return None


def chargers_for_route(
    daily_km: float,
    route_lat: float | None,
    route_lon: float | None,
    fallback: int,
) -> tuple[int, bool]:
    """Resolve the charger count for a route, preferring live map data.

    Returns ``(count, is_live)``. When coordinates are supplied and the OpenStreetMap
    query succeeds, ``is_live`` is True; otherwise the static ``fallback`` is used.
    The search radius scales with the route so it covers the realistic operating area.
    """
    if route_lat is not None and route_lon is not None:
        radius = max(15.0, min(daily_km / 2.0, 80.0))
        live = live_chargers_near(round(route_lat, 3), round(route_lon, 3), round(radius, 1))
        if live is not None:
            return live, True
    return fallback, False


@dataclass
class RouteAssessment:
    """Whether an EV can serve a route, and why."""

    ev_viable: bool
    stops_needed: int          # en-route rapid charges the route requires
    chargers_available: int    # rapid chargers known along the route
    charge_minutes: float      # extra time per day spent charging en route
    note: str                  # human-readable explanation
    chargers_live: bool = False  # True if chargers_available came from live map data


def assess_ev_route(
    daily_km: float,
    ev_range_km: float,
    depot_charging: bool,
    chargers_on_route: int,
    chargers_live: bool = False,
) -> RouteAssessment:
    """Decide if an EV can cover ``daily_km`` given its range and charging options."""
    src = "live map" if chargers_live else "estimate"
    usable = ev_range_km * USABLE_RANGE_FRAC
    if usable <= 0:
        return RouteAssessment(False, 0, chargers_on_route, 0.0,
                               "No EV range data available for this route.", chargers_live)

    # The route fits within a single charge: depot top-up overnight is enough.
    if daily_km <= usable:
        if depot_charging:
            return RouteAssessment(
                True, 0, chargers_on_route, 0.0,
                f"{daily_km:.0f} km/day fits the {usable:.0f} km usable range — "
                "charges overnight at the depot, no public chargers needed.", chargers_live)
        if chargers_on_route >= 1:
            return RouteAssessment(
                True, 1, chargers_on_route, RAPID_CHARGE_MIN,
                f"{daily_km:.0f} km/day; no depot charger, but {chargers_on_route} "
                f"charger(s) on the route ({src}) cover a daytime top-up "
                f"(+{RAPID_CHARGE_MIN:.0f} min).", chargers_live)
        return RouteAssessment(
            False, 1, 0, 0.0,
            f"{daily_km:.0f} km/day but no depot charger and no chargers on the route "
            f"({src}) — EV cannot be reliably refuelled.", chargers_live)

    # The route exceeds one charge: count the en-route stops needed.
    stops = math.ceil(daily_km / usable) - 1
    if chargers_on_route >= stops:
        mins = stops * RAPID_CHARGE_MIN
        return RouteAssessment(
            True, stops, chargers_on_route, mins,
            f"{daily_km:.0f} km/day exceeds the {usable:.0f} km range; {stops} rapid "
            f"stop(s) needed and {chargers_on_route} charger(s) available en route "
            f"({src}, +{mins:.0f} min/day).", chargers_live)
    return RouteAssessment(
        False, stops, chargers_on_route, 0.0,
        f"{daily_km:.0f} km/day needs {stops} charging stop(s) but only "
        f"{chargers_on_route} charger(s) are on the route ({src}) — keep the current "
        "vehicle until charging is deployed.", chargers_live)
