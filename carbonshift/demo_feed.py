"""Live demo data feed.

During a demo you can "dump" new organizational data into the running dashboard
without restarting it. This module reads a JSON file (``demo_inject.json`` at the
project root by default, override with ``DEMO_INJECT_PATH``) and turns it into the
same model objects the agents already reason about. The dashboard appends these to
its baseline data on every refresh, so newly-added purchases/vehicles/trips flow
straight through the multi-agent pipeline — the agents pick them up and act.

The file is optional: when it is missing or empty the dashboard simply shows its
baseline demo data. ``data_version`` is a cheap fingerprint (file size + mtime) the
dashboard polls so it can re-render the moment the file changes.

Expected JSON shape (every section optional)::

    {
      "purchases": [
        {"name": "Trade-show booth hardware", "kg_co2e": 5200, "cost": 16000},
        {"name": "Branded staff uniforms", "cost": 9000}
      ],
      "vehicles": [
        {"name": "Bristol delivery van", "daily_km": 110, "fuel": "diesel",
         "ev_range_km": 250, "depot_charging": true,
         "route_lat": 51.4545, "route_lon": -2.5879}
      ],
      "trips": [
        {"name": "Investor roadshow, Edinburgh", "distance_km": 540,
         "mode": "car_petrol", "essential": false}
      ],
      "jobs": [
        {"name": "Quarterly risk-model backtest", "power_kw": 80,
         "duration_hours": 3, "due_in_hours": 18}
      ],
      "grid_spike": 180
    }

Compute jobs use ``due_in_hours`` (relative to the planning moment) rather than an
absolute deadline, so the demo always has a live, in-range window to optimise into.
``grid_spike`` (gCO₂/kWh, optional) simulates a grid-stress event from the backend
so the agents re-plan live — no UI control needed.

A purchase line may omit ``kg_co2e``: its embodied carbon is then estimated from
``cost`` via published spend-based emission factors (see ``emission_factors.py``).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from .emission_factors import estimate_embodied_kg
from .models import FuelType, Job, PurchaseLine, TravelMode, Trip, Vehicle


def _inject_path() -> str:
    """Resolve the injection file path (env override or project-root default)."""
    env = os.environ.get("DEMO_INJECT_PATH")
    if env:
        return env
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "demo_inject.json")


def data_version() -> str:
    """Cheap fingerprint of the injection file so the UI can detect changes.

    Returns ``"0"`` when no file is present. Reads only file metadata, never the
    full pipeline, so it is safe to poll frequently.
    """
    path = _inject_path()
    try:
        st = os.stat(path)
        return f"{int(st.st_size)}-{int(st.st_mtime)}"
    except OSError:
        return "0"


def injected_spike() -> float:
    """Read the simulated grid-spike value (gCO2/kWh) from the injection file.

    Returns ``0.0`` when no file is present or no spike is set. This lets a backend
    script trigger a grid-stress event so the agents re-plan live, without exposing
    a fabricate-data control on the production dashboard.
    """
    path = _inject_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return max(0.0, float(raw.get("grid_spike", 0.0)))
    except (OSError, ValueError, TypeError):
        return 0.0


def _to_purchase(d: dict) -> PurchaseLine:
    cost = float(d.get("cost", 0.0))
    # Embodied carbon: use a supplied measured/estimated figure when present, else
    # derive it from spend via published spend-based emission factors (real-world
    # EEIO method) so a line only needs {name, cost} to get a defensible footprint.
    if d.get("kg_co2e") is not None:
        kg_co2e = float(d["kg_co2e"])
    else:
        kg_co2e, _source = estimate_embodied_kg(str(d["name"]), cost)
    return PurchaseLine(
        name=str(d["name"]),
        kg_co2e=kg_co2e,
        cost=cost,
        # Omit alt_reduction_pct (leave None) to trigger autonomous agent reasoning.
        alt_reduction_pct=(
            float(d["alt_reduction_pct"]) if d.get("alt_reduction_pct") is not None else None
        ),
        alt_cost_delta_pct=float(d.get("alt_cost_delta_pct", 0.0)),
        alternative=str(d.get("alternative", "Lower-carbon alternative")),
        locked=bool(d.get("locked", False)),
    )


def _to_vehicle(d: dict) -> Vehicle:
    return Vehicle(
        name=str(d["name"]),
        daily_km=float(d["daily_km"]),
        fuel=FuelType(str(d.get("fuel", "diesel")).lower()),
        swappable_to_ev=bool(d.get("swappable_to_ev", True)),
        days_per_week=int(d.get("days_per_week", 5)),
        ev_range_km=float(d.get("ev_range_km", 250.0)),
        chargers_on_route=int(d.get("chargers_on_route", 0)),
        depot_charging=bool(d.get("depot_charging", True)),
        route_lat=(float(d["route_lat"]) if d.get("route_lat") is not None else None),
        route_lon=(float(d["route_lon"]) if d.get("route_lon") is not None else None),
    )


def _to_trip(d: dict) -> Trip:
    return Trip(
        name=str(d["name"]),
        distance_km=float(d["distance_km"]),
        mode=TravelMode(str(d.get("mode", "car_petrol")).lower()),
        passengers=int(d.get("passengers", 1)),
        round_trip=bool(d.get("round_trip", True)),
        essential=bool(d.get("essential", False)),
        relationship_critical=bool(d.get("relationship_critical", False)),
    )


def _to_job(d: dict, now: datetime) -> Job:
    """Build a deferrable compute Job from injected JSON.

    Deadline is given relative to the planning moment via ``due_in_hours`` so the
    job always has a real, in-range window for the OptimizerAgent to schedule into.
    An absolute ``deadline`` (ISO 8601) is also honoured if supplied.
    """
    if d.get("deadline"):
        deadline = datetime.fromisoformat(str(d["deadline"]))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
    else:
        deadline = now + timedelta(hours=float(d.get("due_in_hours", 12.0)))
    return Job(
        name=str(d["name"]),
        power_kw=float(d["power_kw"]),
        duration_hours=float(d["duration_hours"]),
        deadline=deadline,
        earliest_start=now,
        region=str(d.get("region", "national")),
        flexible=bool(d.get("flexible", True)),
    )


def load_injected(now: datetime | None = None) -> dict:
    """Read and parse the injection file into model objects.

    Returns a dict with ``purchases``, ``vehicles``, ``trips`` and ``jobs`` lists
    (each empty when not supplied). ``now`` anchors relative compute-job deadlines.
    Never raises: a malformed file yields empty lists so the dashboard keeps
    running on its baseline data.
    """
    empty = {"purchases": [], "vehicles": [], "trips": [], "jobs": []}
    now = now or datetime.now(timezone.utc)
    path = _inject_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return empty

    out = dict(empty)
    try:
        out["purchases"] = [_to_purchase(x) for x in raw.get("purchases", [])]
        out["vehicles"] = [_to_vehicle(x) for x in raw.get("vehicles", [])]
        out["trips"] = [_to_trip(x) for x in raw.get("trips", [])]
        out["jobs"] = [_to_job(x, now) for x in raw.get("jobs", [])]
    except (KeyError, TypeError, ValueError):
        # Partial parse: keep whatever succeeded, drop the rest.
        pass
    return out
