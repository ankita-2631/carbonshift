"""Business-travel data source.

In production, CarbonShift pulls upcoming trips from the organization's travel
booking app (e.g. SAP Concur, TravelPerk, Egencia) via its API. Set the
``TRAVEL_APP_API`` environment variable to a JSON endpoint that returns a list of
bookings; each booking is mapped to a :class:`Trip`.

When no endpoint is configured (or it is unreachable), CarbonShift falls back to the
bundled demo trips so the demo always runs.

Expected booking JSON (per item)::

    {
        "name": "Quarterly review, London HQ",
        "distance_km": 320.0,
        "mode": "car_petrol",      # car_petrol | car_ev | rail | virtual
        "passengers": 1,
        "round_trip": true,
        "essential": false
    }
"""
from __future__ import annotations

import os

import requests

from .models import Trip, TravelMode
from .sample_data import demo_trips

TRAVEL_APP_API = os.environ.get("TRAVEL_APP_API", "")
TRAVEL_APP_TOKEN = os.environ.get("TRAVEL_APP_TOKEN", "")


class TripSource:
    """Trips plus a label describing where they came from."""

    def __init__(self, trips: list[Trip], source: str):
        self.trips = trips
        self.source = source


def _booking_to_trip(b: dict) -> Trip:
    raw_mode = str(b.get("mode", "car_petrol")).lower()
    try:
        mode = TravelMode(raw_mode)
    except ValueError:
        mode = TravelMode.CAR_PETROL
    return Trip(
        name=str(b["name"]),
        distance_km=float(b["distance_km"]),
        mode=mode,
        passengers=int(b.get("passengers", 1)),
        round_trip=bool(b.get("round_trip", True)),
        essential=bool(b.get("essential", False)),
    )


def get_trips() -> TripSource:
    """Pull upcoming trips from the org travel app, or fall back to demo data."""
    if not TRAVEL_APP_API:
        return TripSource(demo_trips(), source="demo-trips (no travel app configured)")
    try:
        headers = {"Authorization": f"Bearer {TRAVEL_APP_TOKEN}"} if TRAVEL_APP_TOKEN else {}
        resp = requests.get(TRAVEL_APP_API, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        bookings = data.get("bookings", data) if isinstance(data, dict) else data
        trips = [_booking_to_trip(b) for b in bookings]
        if not trips:
            return TripSource(demo_trips(), source="demo-trips (travel app returned none)")
        return TripSource(trips, source=f"travel-app: {TRAVEL_APP_API}")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return TripSource(demo_trips(), source="demo-trips (travel app unavailable)")
