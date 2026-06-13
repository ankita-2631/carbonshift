"""Sample workloads for the CarbonShift demo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Facility, FuelType, Job, PurchaseLine, Trip, TravelMode, Vehicle


def demo_jobs(now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(timezone.utc)
    return [
        Job(
            name="Nightly model fine-tune (GPU cluster)",
            power_kw=120.0,
            duration_hours=4.0,
            deadline=now + timedelta(hours=14),
            earliest_start=now,
            flexible=True,
        ),
        Job(
            name="Data-warehouse ETL batch",
            power_kw=45.0,
            duration_hours=2.0,
            deadline=now + timedelta(hours=10),
            earliest_start=now,
            flexible=True,
        ),
        Job(
            name="Customer-facing API (always on)",
            power_kw=15.0,
            duration_hours=1.0,
            deadline=now + timedelta(hours=1),
            earliest_start=now,
            flexible=False,
        ),
    ]


def tight_jobs(now: datetime | None = None) -> list[Job]:
    """A high-pressure scenario: tight deadlines leave little room to shift.

    Demonstrates the agents correctly finding fewer/smaller savings and rating more
    jobs AMBER/RED when the grid's clean windows fall outside what deadlines allow.
    """
    now = now or datetime.now(timezone.utc)
    return [
        Job(
            name="Nightly model fine-tune (GPU cluster)",
            power_kw=120.0,
            duration_hours=4.0,
            deadline=now + timedelta(hours=5),   # must finish soon
            earliest_start=now,
            flexible=True,
        ),
        Job(
            name="EV fleet charging (depot)",
            power_kw=300.0,
            duration_hours=6.0,
            deadline=now + timedelta(hours=7),   # almost no slack
            earliest_start=now,
            flexible=True,
        ),
        Job(
            name="Data-warehouse ETL batch",
            power_kw=45.0,
            duration_hours=2.0,
            deadline=now + timedelta(hours=3),   # tight
            earliest_start=now,
            flexible=True,
        ),
        Job(
            name="Customer-facing API (always on)",
            power_kw=15.0,
            duration_hours=1.0,
            deadline=now + timedelta(hours=1),
            earliest_start=now,
            flexible=False,
        ),
    ]


SCENARIOS = {
    "relaxed": demo_jobs,
    "tight": tight_jobs,
}


def demo_trips() -> list[Trip]:
    """A set of business trips for the TravelAgent to optimise."""
    return [
        Trip(
            name="Quarterly review, London HQ",
            distance_km=320.0,
            mode=TravelMode.CAR_PETROL,
            passengers=1,
            round_trip=True,
            essential=False,
        ),
        Trip(
            name="Client pitch, Manchester",
            distance_km=140.0,
            mode=TravelMode.CAR_PETROL,
            passengers=3,
            round_trip=True,
            essential=True,
        ),
        Trip(
            name="Weekly partner sync",
            distance_km=85.0,
            mode=TravelMode.CAR_PETROL,
            passengers=1,
            round_trip=True,
            essential=False,
            relationship_critical=True,
        ),
    ]


def demo_facilities() -> list[Facility]:
    """On-site energy loads the FacilitiesAgent can reduce (Scope 1 + 2)."""
    return [
        Facility(name="HQ HVAC", daily_kwh=900.0, reducible_pct=0.22,
                 measure="Smart HVAC setpoint + scheduling"),
        Facility(name="Office lighting", daily_kwh=260.0, reducible_pct=0.45,
                 measure="LED retrofit + daylight/occupancy sensors"),
        Facility(name="Server room cooling", daily_kwh=540.0, reducible_pct=0.18,
                 measure="Raise cold-aisle setpoint + airflow containment"),
        Facility(name="Warehouse gas heating", daily_kwh=1200.0, reducible_pct=0.15,
                 measure="Destratification fans + zoning", gas=True),
    ]


def demo_vehicles() -> list[Vehicle]:
    """Fleet/commute vehicles the FleetAgent can reason about (Scope 1 + 3).

    Each vehicle carries the coordinates of its operating area; the FleetAgent queries
    the live Open Charge Map API for the real number of fast/rapid chargers there. A
    deliberate geographic mix makes the route + charging logic visible:
      * dense-city routes (London, Manchester, Birmingham) with many real chargers,
      * a long regional route that exceeds EV range but is covered by en-route chargers,
      * a remote Highlands route where real charger density is low,
      * a heavy haulage truck with no EV equivalent — kept regardless of route.
    The electrify/keep verdict therefore reflects live charging infrastructure.
    """
    return [
        Vehicle(name="Delivery van #1 (London)", daily_km=120.0, fuel=FuelType.DIESEL,
                swappable_to_ev=True, days_per_week=6,
                ev_range_km=250.0, chargers_on_route=3, depot_charging=True,
                route_lat=51.5074, route_lon=-0.1278),
        Vehicle(name="Rural long-haul van (Highlands)", daily_km=420.0, fuel=FuelType.DIESEL,
                swappable_to_ev=True, days_per_week=5,
                ev_range_km=250.0, chargers_on_route=0, depot_charging=True,
                route_lat=57.4778, route_lon=-4.2247),
        Vehicle(name="Heavy haulage truck", daily_km=200.0, fuel=FuelType.DIESEL,
                swappable_to_ev=False, days_per_week=5,
                ev_range_km=0.0, chargers_on_route=0, depot_charging=True),
    ]


def demo_purchases() -> list[PurchaseLine]:
    """Purchased goods/services the ProcurementAgent can switch (Scope 3)."""
    return [
        PurchaseLine(name="Office paper", kg_co2e=3200.0, cost=4000.0,
                     alt_reduction_pct=0.40, alt_cost_delta_pct=-0.05,
                     alternative="100% recycled paper"),
        PurchaseLine(name="Laptops (annual refresh)", kg_co2e=14000.0, cost=90000.0,
                     alt_reduction_pct=0.30, alt_cost_delta_pct=0.0,
                     alternative="refurbished + extended-life devices"),
        PurchaseLine(name="Specialist reagents", kg_co2e=5000.0, cost=22000.0,
                     alt_reduction_pct=0.0, alternative="(single-source)", locked=True),
    ]

