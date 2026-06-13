"""CarbonShift demo data-injection script.

Run this DURING a live demo to "dump" new organizational data into the already-running
dashboard. The dashboard polls for changes every few seconds and re-plans automatically:
new purchases flow through the autonomous ProcurementAgent (which reasons about unknown
items via Foundry IQ), new vehicles flow through the route- & charging-aware FleetAgent,
new trips through the TravelAgent, and new compute jobs through the OptimizerAgent (which
slots them into the greenest grid window before their deadline) — all live, no restart.

Usage (from anywhere):
    python C:\\Hack\\carbonshift\\demo_inject.py            # dump the next wave of data
    python C:\\Hack\\carbonshift\\demo_inject.py wave 2     # dump a specific wave
    python C:\\Hack\\carbonshift\\demo_inject.py spike      # simulate a grid-stress event (180 gCO2/kWh)
    python C:\\Hack\\carbonshift\\demo_inject.py spike 220  # simulate a spike of a specific magnitude
    python C:\\Hack\\carbonshift\\demo_inject.py spike off  # clear the simulated spike
    python C:\\Hack\\carbonshift\\demo_inject.py status     # show what is currently injected
    python C:\\Hack\\carbonshift\\demo_inject.py clear      # reset to baseline (remove all injected data)

Each wave is ADDITIVE: it appends to whatever has already been dumped, so you can build
the picture up live. The grid spike is driven from here (not the dashboard) so the
production view never exposes a fabricate-data control. `clear` wipes it back to the
baseline demo dataset.
"""
from __future__ import annotations

import json
import os
import sys

# The dashboard reads this file (override with DEMO_INJECT_PATH to match the server).
INJECT_PATH = os.environ.get(
    "DEMO_INJECT_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_inject.json")
)

# Curated waves. Each wave adds items the agents have never seen, so the audience can
# watch the multi-agent pipeline assess and act on brand-new data in real time.
WAVES: list[dict] = [
    # Wave 1 — a brand-new procurement item (no vetted alternative) + a new city van.
    {
        "purchases": [
            # No alt_reduction_pct => ProcurementAgent reasons autonomously (✦ AI).
            {"name": "Trade-show booth & exhibition stand", "kg_co2e": 5200.0, "cost": 16000.0},
        ],
        "vehicles": [
            # Short Bristol route, fits EV range, depot charging => electrify (GREEN).
            {"name": "Bristol delivery van", "daily_km": 110.0, "fuel": "diesel",
             "ev_range_km": 250.0, "depot_charging": True,
             "route_lat": 51.4545, "route_lon": -2.5879},
        ],
    },
    # Wave 2 — a high-impact unknown purchase + a long route that needs live charger data
    # + a fresh deferrable compute job the OptimizerAgent must schedule into clean power.
    {
        "purchases": [
            {"name": "Server hardware refresh (data centre)", "kg_co2e": 18000.0, "cost": 120000.0},
        ],
        "vehicles": [
            # Long Cardiff↔Newcastle style route: exceeds range, relies on live chargers.
            {"name": "Inter-city logistics route", "daily_km": 470.0, "fuel": "diesel",
             "ev_range_km": 250.0, "depot_charging": True,
             "route_lat": 53.8008, "route_lon": -1.5491},
        ],
        "jobs": [
            # Flexible GPU batch job, 18h deadline => OptimizerAgent shifts it to the
            # greenest grid window (GREEN) while the RiskAgent guarantees the deadline.
            {"name": "Quarterly risk-model backtest", "power_kw": 80.0,
             "duration_hours": 3.0, "due_in_hours": 18.0, "flexible": True},
        ],
    },
    # Wave 3 — new long-haul trips the TravelAgent must reason about. Names are left
    # deliberately descriptive (and flags OFF) so the AI classifier decides the in-person
    # need itself: a site inspection should read as ESSENTIAL, an investor roadshow as
    # RELATIONSHIP-CRITICAL, and a routine internal review as flexible (can go virtual).
    {
        "trips": [
            # Should classify ESSENTIAL — physical inspection cannot be done virtually.
            {"name": "Factory equipment inspection, Sheffield", "distance_km": 230.0,
             "mode": "car_petrol"},
            # Should classify RELATIONSHIP-CRITICAL — investor roadshow, prefer in person.
            {"name": "Investor roadshow, Edinburgh", "distance_km": 540.0,
             "mode": "car_petrol"},
            # Should classify FLEXIBLE — routine internal review, can go virtual.
            {"name": "Monthly internal budget review", "distance_km": 180.0,
             "mode": "car_petrol"},
        ],
        "purchases": [
            {"name": "Branded staff uniforms", "kg_co2e": 3100.0, "cost": 9000.0},
        ],
    },
]


def _load() -> dict:
    try:
        with open(INJECT_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault("purchases", [])
    data.setdefault("vehicles", [])
    data.setdefault("trips", [])
    data.setdefault("jobs", [])
    data.setdefault("_waves_applied", [])
    return data


def _save(data: dict) -> None:
    with open(INJECT_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _counts(data: dict) -> str:
    return (f"{len(data['purchases'])} purchase(s), {len(data['vehicles'])} vehicle(s), "
            f"{len(data['trips'])} trip(s), {len(data['jobs'])} job(s)")


def apply_wave(n: int) -> None:
    if n < 1 or n > len(WAVES):
        print(f"No wave {n}. Available waves: 1-{len(WAVES)}.")
        return
    data = _load()
    wave = WAVES[n - 1]
    for key in ("purchases", "vehicles", "trips", "jobs"):
        data[key].extend(wave.get(key, []))
    data["_waves_applied"].append(n)
    _save(data)
    added = ", ".join(
        f"{len(wave.get(k, []))} {k[:-1]}{'s' if len(wave.get(k, [])) != 1 else ''}"
        for k in ("purchases", "vehicles", "trips", "jobs") if wave.get(k)
    )
    print(f"Dumped wave {n} ({added}). Dashboard now carries: {_counts(data)}.")
    print("Watch the dashboard — the agents will re-plan within a few seconds.")


def next_wave() -> None:
    data = _load()
    applied = set(data.get("_waves_applied", []))
    for i in range(1, len(WAVES) + 1):
        if i not in applied:
            apply_wave(i)
            return
    print("All waves already dumped. Use 'clear' to reset to baseline.")


def clear() -> None:
    try:
        os.remove(INJECT_PATH)
        print("Cleared injected data — dashboard reset to its baseline dataset.")
    except FileNotFoundError:
        print("Nothing to clear; already at baseline.")


def status() -> None:
    data = _load()
    spike = float(data.get("grid_spike", 0) or 0)
    if not (data["purchases"] or data["vehicles"] or data["trips"] or data["jobs"] or spike):
        print("Baseline only — no data injected. Run with no args to dump the first wave.")
        return
    print(f"Injected: {_counts(data)} (waves applied: {data.get('_waves_applied', [])}).")
    if spike:
        print(f"  · [grid spike] +{spike:g} gCO2/kWh simulated")
    for key in ("purchases", "vehicles", "trips", "jobs"):
        for item in data[key]:
            print(f"  · [{key[:-1]}] {item.get('name')}")


def set_spike(value: float) -> None:
    """Simulate a grid-stress event the agents must re-plan around (gCO2/kWh)."""
    data = _load()
    if value <= 0:
        data.pop("grid_spike", None)
        _save(data)
        print("Cleared the simulated grid spike — dashboard reverts to the live grid.")
        return
    data["grid_spike"] = value
    _save(data)
    print(f"Simulated grid spike: +{value:g} gCO2/kWh. The agents will re-plan within a few seconds.")


def main(argv: list[str]) -> None:
    if not argv:
        next_wave()
        return
    cmd = argv[0].lower()
    if cmd == "clear":
        clear()
    elif cmd == "status":
        status()
    elif cmd == "spike":
        if len(argv) > 1 and argv[1].lower() in ("off", "clear", "0"):
            set_spike(0.0)
        elif len(argv) > 1:
            try:
                set_spike(float(argv[1]))
            except ValueError:
                print("Usage: demo_inject.py spike [value|off]")
        else:
            set_spike(180.0)
    elif cmd == "wave" and len(argv) > 1 and argv[1].isdigit():
        apply_wave(int(argv[1]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
