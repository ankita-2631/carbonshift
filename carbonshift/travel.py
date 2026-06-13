"""Travel optimizer.

Given a trip, evaluate each travel mode's CO2 and cost, and recommend the cleanest
option that respects business constraints (e.g. an essential trip cannot go virtual).
Emission and cost factors are transparent, citable estimates — not a live feed.
"""
from __future__ import annotations

from .models import RiskLevel, Trip, TravelDecision, TravelMode, TravelPlan
from .travel_classifier import classify_trip

# gCO2 per passenger-km, typical UK figures. Cite "Travel Emission Factors".
EMISSION_FACTORS_G_PER_KM: dict[TravelMode, float] = {
    TravelMode.CAR_PETROL: 170.0,
    TravelMode.CAR_EV: 47.0,
    TravelMode.RAIL: 35.0,
    TravelMode.VIRTUAL: 0.1,   # energy of a video call, effectively negligible
}

# Cost per km in major currency units (e.g. pounds), rough all-in estimates.
COST_PER_KM: dict[TravelMode, float] = {
    TravelMode.CAR_PETROL: 0.25,   # fuel + wear
    TravelMode.CAR_EV: 0.10,
    TravelMode.RAIL: 0.18,         # ticket
    TravelMode.VIRTUAL: 0.0,
}

# Below this % saving we rate AMBER; at/above we rate GREEN.
GREEN_THRESHOLD_PCT = 15.0


def _effective_km(trip: Trip) -> float:
    return trip.distance_km * (2.0 if trip.round_trip else 1.0)


def _kg_co2(trip: Trip, mode: TravelMode) -> float:
    """Total kg CO2 for the trip by a given mode (per-person factor x passengers)."""
    km = _effective_km(trip)
    # Car emissions are per-vehicle: shared by passengers. Rail/virtual are per-person.
    per_person = EMISSION_FACTORS_G_PER_KM[mode] * km
    if mode in (TravelMode.CAR_PETROL, TravelMode.CAR_EV):
        grams = per_person  # one vehicle regardless of occupancy
    else:
        grams = per_person * max(1, trip.passengers)
    return grams / 1000.0


def _cost(trip: Trip, mode: TravelMode) -> float:
    km = _effective_km(trip)
    if mode in (TravelMode.CAR_PETROL, TravelMode.CAR_EV):
        return COST_PER_KM[mode] * km  # per vehicle
    return COST_PER_KM[mode] * km * max(1, trip.passengers)  # per ticket


def optimize_trip(trip: Trip, keep_physical: bool = False) -> TravelDecision:
    """Pick the lowest-CO2 mode for a trip, honouring the essential constraint.

    If ``keep_physical`` is set, the trip is not downgraded to a virtual meeting even
    when that would be cleaner — used when travel policy wants to preserve in-person
    contact for a relationship-critical trip.
    """
    # The agent reasons about *why* the trip is needed (site work vs. routine sync) and
    # may add an in-person requirement. Human-set flags are an authoritative floor.
    classification = classify_trip(trip)
    trip.essential = trip.essential or bool(classification.get("essential"))
    trip.relationship_critical = (
        trip.relationship_critical or bool(classification.get("relationship_critical"))
    )
    class_citations = list(classification.get("citations", []))
    class_rationale = classification.get("rationale", "")

    baseline_mode = trip.mode
    baseline_kg = _kg_co2(trip, baseline_mode)
    baseline_cost = _cost(trip, baseline_mode)

    # Candidate modes: drop virtual if the trip is essential (must be in person) or
    # policy requires keeping it physical.
    candidates = list(EMISSION_FACTORS_G_PER_KM.keys())
    if trip.essential or keep_physical:
        candidates = [m for m in candidates if m != TravelMode.VIRTUAL]

    best_mode = baseline_mode
    best_kg = baseline_kg
    for mode in candidates:
        kg = _kg_co2(trip, mode)
        if kg < best_kg:
            best_kg = kg
            best_mode = mode

    chosen_cost = _cost(trip, best_mode)
    saved_pct = 0.0 if baseline_kg <= 0 else 100.0 * (baseline_kg - best_kg) / baseline_kg

    if best_mode == baseline_mode:
        risk = RiskLevel.AMBER if trip.essential else RiskLevel.GREEN
        rationale = "Current mode is already the cleanest available option."
    elif best_mode == TravelMode.VIRTUAL:
        risk = RiskLevel.GREEN
        rationale = (
            f"This trip can be replaced by a virtual meeting, avoiding the journey "
            f"entirely ({baseline_kg:.1f} kg CO2 saved)."
        )
    elif saved_pct >= GREEN_THRESHOLD_PCT:
        risk = RiskLevel.GREEN
        rationale = (
            f"Switching from {baseline_mode.value} to {best_mode.value} cuts emissions "
            f"from {baseline_kg:.1f} to {best_kg:.1f} kg CO2."
        )
    else:
        risk = RiskLevel.AMBER
        rationale = (
            f"A modest improvement is available by switching to {best_mode.value}."
        )

    return TravelDecision(
        trip=trip,
        chosen_mode=best_mode,
        baseline_mode=baseline_mode,
        kg_co2_chosen=best_kg,
        kg_co2_baseline=baseline_kg,
        cost_chosen=chosen_cost,
        cost_baseline=baseline_cost,
        risk=risk,
        rationale=rationale,
        citations=class_citations,
        ai_classified=True,
        classification_note=class_rationale,
    )


def optimize_travel(
    trips: list[Trip], keep_physical: set[str] | None = None
) -> TravelPlan:
    """Optimize a list of trips independently and aggregate the savings.

    ``keep_physical`` is a set of trip names that policy requires to stay in a
    physical mode (no virtual downgrade).
    """
    keep_physical = keep_physical or set()
    plan = TravelPlan()
    for trip in trips:
        plan.decisions.append(
            optimize_trip(trip, keep_physical=trip.name in keep_physical)
        )
    return plan
