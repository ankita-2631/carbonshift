"""Grid carbon-intensity data source.

Uses the UK National Grid ESO Carbon Intensity API (no API key required):
https://api.carbonintensity.org.uk/

Falls back to a deterministic synthetic forecast when the network is unavailable,
so the demo always runs.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

import requests

CARBON_API_BASE = os.environ.get("CARBON_API_BASE", "https://api.carbonintensity.org.uk")

# (start, end) -> gCO2/kWh forecast point
IntensityPoint = tuple[datetime, datetime, float]


class CarbonForecast:
    """A 48-hour carbon-intensity forecast in 30-minute slots."""

    def __init__(self, points: list[IntensityPoint], source: str):
        self.points = sorted(points, key=lambda p: p[0])
        self.source = source

    def average_intensity(self, start: datetime, duration_hours: float) -> float:
        """Average gCO2/kWh over [start, start+duration]."""
        end = start + timedelta(hours=duration_hours)
        overlapping = [
            gco2
            for (p_start, p_end, gco2) in self.points
            if p_end > start and p_start < end
        ]
        if not overlapping:
            # Out of forecast range: use the nearest known point.
            return self.points[-1][2] if self.points else 250.0
        return sum(overlapping) / len(overlapping)

    def window_bounds(self) -> tuple[datetime, datetime]:
        return self.points[0][0], self.points[-1][1]


def _synthetic_forecast(now: datetime) -> CarbonForecast:
    """Deterministic day/night curve: dirtier in evening peak, cleaner overnight/midday."""
    points: list[IntensityPoint] = []
    base = now.replace(minute=0, second=0, microsecond=0)
    for i in range(96):  # 48h of 30-min slots
        slot_start = base + timedelta(minutes=30 * i)
        hour = slot_start.hour + slot_start.minute / 60.0
        # Peak ~18:00 (dirty ~330), trough ~04:00 and ~13:00 (clean ~120).
        evening = 105 * math.exp(-((hour - 18) ** 2) / 6)
        midday_dip = -60 * math.exp(-((hour - 13) ** 2) / 4)
        overnight = -40 * math.exp(-((hour - 4) ** 2) / 8)
        gco2 = 220 + evening + midday_dip + overnight
        points.append((slot_start, slot_start + timedelta(minutes=30), round(gco2, 1)))
    return CarbonForecast(points, source="synthetic-fallback")


def get_forecast(region: str = "national", now: datetime | None = None) -> CarbonForecast:
    """Fetch a 48h carbon-intensity forecast, falling back to synthetic data on error."""
    now = now or datetime.now(timezone.utc)
    try:
        start = now.strftime("%Y-%m-%dT%H:%MZ")
        end = (now + timedelta(hours=47)).strftime("%Y-%m-%dT%H:%MZ")
        url = f"{CARBON_API_BASE}/intensity/{start}/{end}"
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        points: list[IntensityPoint] = []
        for row in data:
            p_start = datetime.fromisoformat(row["from"].replace("Z", "+00:00"))
            p_end = datetime.fromisoformat(row["to"].replace("Z", "+00:00"))
            gco2 = row["intensity"].get("forecast")
            if gco2 is not None:
                points.append((p_start, p_end, float(gco2)))
        if points:
            return CarbonForecast(points, source=f"{CARBON_API_BASE}/intensity (forecast)")
    except Exception:
        pass
    return _synthetic_forecast(now)
