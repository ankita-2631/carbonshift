"""Facilities optimizer (Scope 1 + 2).

Estimates the CO2 and cost a building-efficiency measure avoids. Grid electricity is
valued at the day's average carbon intensity and the price model; on-site gas uses a
fixed emission factor and price. Figures are transparent estimates, not a live feed.
"""
from __future__ import annotations

from .models import Facility, MeasureDecision, MeasurePlan, RiskLevel
from .pricing import price_p_per_kwh

# On-site natural gas: emission factor and price (cite "Sustainability Reference Data").
GAS_G_PER_KWH = 184.0
GAS_PRICE_P_PER_KWH = 7.0

GREEN_THRESHOLD_PCT = 15.0


def _energy_kg_and_cost(daily_kwh: float, intensity_gco2: float, gas: bool) -> tuple[float, float]:
    """Daily kg CO2 and cost (currency units) for an energy load."""
    if gas:
        kg = daily_kwh * GAS_G_PER_KWH / 1000.0
        cost = daily_kwh * GAS_PRICE_P_PER_KWH / 100.0
    else:
        kg = daily_kwh * intensity_gco2 / 1000.0
        cost = daily_kwh * price_p_per_kwh(intensity_gco2) / 100.0
    return kg, cost


def optimize_facility(facility: Facility, intensity_gco2: float) -> MeasureDecision:
    base_kg, base_cost = _energy_kg_and_cost(facility.daily_kwh, intensity_gco2, facility.gas)
    saved_fraction = max(0.0, min(1.0, facility.reducible_pct))
    chosen_kwh = facility.daily_kwh * (1.0 - saved_fraction)
    chosen_kg, chosen_cost = _energy_kg_and_cost(chosen_kwh, intensity_gco2, facility.gas)

    pct = saved_fraction * 100.0
    if pct >= GREEN_THRESHOLD_PCT:
        risk = RiskLevel.GREEN
    elif pct > 0:
        risk = RiskLevel.AMBER
    else:
        risk = RiskLevel.RED

    rationale = (
        f"{facility.measure} cuts about {pct:.0f}% of this load's daily energy "
        f"({base_kg:.1f} → {chosen_kg:.1f} kg CO2/day)."
    )
    return MeasureDecision(
        name=facility.name,
        domain="facilities",
        action=facility.measure,
        kg_co2_baseline=base_kg,
        kg_co2_chosen=chosen_kg,
        cost_baseline=base_cost,
        cost_chosen=chosen_cost,
        risk=risk,
        rationale=rationale,
    )


def optimize_facilities(facilities: list[Facility], intensity_gco2: float) -> MeasurePlan:
    plan = MeasurePlan(domain="facilities")
    for f in facilities:
        plan.decisions.append(optimize_facility(f, intensity_gco2))
    return plan
