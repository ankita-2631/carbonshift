"""Fleet optimizer (Scope 1 + 3).

Evaluates electrifying owned vehicles / logistics routes / grey-fleet commuting.
The EV-vs-combustion decision is route-aware: it checks each vehicle's daily route
against the candidate EV's range and the charging stations available along the way
(see :mod:`carbonshift.routing`). Emission and cost factors are transparent estimates,
cited to the reference data.
"""
from __future__ import annotations

from .models import FuelType, MeasureDecision, MeasurePlan, RiskLevel, Vehicle
from .routing import USABLE_RANGE_FRAC, assess_ev_route, chargers_for_route

# gCO2 per vehicle-km. Cite "Sustainability Reference Data".
EMISSION_G_PER_KM: dict[FuelType, float] = {
    FuelType.DIESEL: 200.0,
    FuelType.PETROL: 180.0,
    FuelType.EV: 47.0,
}

# Cost per km (fuel/energy + wear), currency units.
COST_PER_KM: dict[FuelType, float] = {
    FuelType.DIESEL: 0.22,
    FuelType.PETROL: 0.25,
    FuelType.EV: 0.08,
}

WEEKS_PER_YEAR = 52
GREEN_THRESHOLD_PCT = 15.0


def _annual_km(vehicle: Vehicle) -> float:
    return vehicle.daily_km * max(0, vehicle.days_per_week) * WEEKS_PER_YEAR


def optimize_vehicle(vehicle: Vehicle) -> MeasureDecision:
    km = _annual_km(vehicle)
    base_kg = km * EMISSION_G_PER_KM[vehicle.fuel] / 1000.0
    base_cost = km * COST_PER_KM[vehicle.fuel]

    # 1) Can this vehicle class be electrified at all?
    class_swappable = vehicle.swappable_to_ev and vehicle.fuel != FuelType.EV

    # 2) Route + charging check: can an EV actually serve this route?
    # Only query live charging-station data when the route genuinely needs en-route
    # charging (i.e. it can't be covered by a single charge + overnight depot top-up).
    # This avoids unnecessary map calls and keeps us within the public API's rate limit.
    usable = vehicle.ev_range_km * USABLE_RANGE_FRAC
    needs_enroute = not (vehicle.daily_km <= usable and vehicle.depot_charging)
    if class_swappable and needs_enroute:
        chargers, chargers_live = chargers_for_route(
            daily_km=vehicle.daily_km,
            route_lat=vehicle.route_lat,
            route_lon=vehicle.route_lon,
            fallback=vehicle.chargers_on_route,
        )
    else:
        chargers, chargers_live = vehicle.chargers_on_route, False
    route = assess_ev_route(
        daily_km=vehicle.daily_km,
        ev_range_km=vehicle.ev_range_km,
        depot_charging=vehicle.depot_charging,
        chargers_on_route=chargers,
        chargers_live=chargers_live,
    )

    can_switch = class_swappable and route.ev_viable

    if can_switch:
        chosen_fuel = FuelType.EV
        action = f"Electrify ({vehicle.fuel.value} → EV)"
    else:
        chosen_fuel = vehicle.fuel
        if not class_swappable:
            action = "Keep current vehicle (no EV model for this class)"
        else:
            action = f"Keep {vehicle.fuel.value} — deploy charging to unlock EV"

    chosen_kg = km * EMISSION_G_PER_KM[chosen_fuel] / 1000.0
    chosen_cost = km * COST_PER_KM[chosen_fuel]
    pct = 0.0 if base_kg <= 0 else 100.0 * (base_kg - chosen_kg) / base_kg

    if not class_swappable:
        risk = RiskLevel.RED
        rationale = "This vehicle class cannot currently be electrified; no change recommended."
        detail = f"{vehicle.daily_km:.0f} km/day · {vehicle.days_per_week} days/wk · no EV equivalent"
    elif not route.ev_viable:
        # An EV is available, but the route/charging blocks the switch — flag it honestly.
        risk = RiskLevel.AMBER
        rationale = (
            f"Electrification is blocked by the route, not the vehicle: {route.note} "
            f"Deploying a charger would unlock a {EMISSION_G_PER_KM[vehicle.fuel] - EMISSION_G_PER_KM[FuelType.EV]:.0f} "
            "gCO2/km cut."
        )
        detail = f"route: {route.note}"
    elif pct >= GREEN_THRESHOLD_PCT:
        risk = RiskLevel.GREEN
        rationale = (
            f"Electrifying this {vehicle.fuel.value} vehicle cuts annual emissions from "
            f"{base_kg:.0f} to {chosen_kg:.0f} kg CO2 over {km:.0f} km/yr."
        )
        detail = f"route: {route.note}"
    else:
        risk = RiskLevel.AMBER
        rationale = "A smaller improvement is available by electrifying this vehicle."
        detail = f"route: {route.note}"

    return MeasureDecision(
        name=vehicle.name,
        domain="fleet",
        action=action,
        kg_co2_baseline=base_kg,
        kg_co2_chosen=chosen_kg,
        cost_baseline=base_cost,
        cost_chosen=chosen_cost,
        risk=risk,
        rationale=rationale,
        detail=detail,
    )


def optimize_fleet(vehicles: list[Vehicle]) -> MeasurePlan:
    plan = MeasurePlan(domain="fleet")
    for v in vehicles:
        plan.decisions.append(optimize_vehicle(v))
    return plan
