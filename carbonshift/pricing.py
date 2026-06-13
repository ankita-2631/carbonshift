"""Electricity price model.

Wholesale electricity price varies through the day and is strongly correlated with
carbon intensity: the dirty evening peak (gas plants) is also the most expensive, while
clean overnight/midday periods are cheaper. This module turns a carbon-intensity point
into an estimated price (in pence per kWh) so the optimizer can report money saved
alongside CO2 saved.

The model is deliberately simple and transparent: a floor price plus a component that
scales with how dirty the grid is. It is an estimate, not a market feed.
"""
from __future__ import annotations

import os

# Currency presentation (symbol only; values are in major units, e.g. pounds).
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "£")

# Pence per kWh: a fixed floor plus a per-(gCO2/kWh) component.
PRICE_FLOOR_P_PER_KWH = float(os.environ.get("PRICE_FLOOR_P_PER_KWH", "12.0"))
PRICE_PER_GCO2 = float(os.environ.get("PRICE_PER_GCO2", "0.06"))


def price_p_per_kwh(intensity_gco2: float) -> float:
    """Estimated price in pence/kWh for a given carbon intensity."""
    return PRICE_FLOOR_P_PER_KWH + PRICE_PER_GCO2 * max(0.0, intensity_gco2)


def energy_cost(power_kw: float, duration_hours: float, intensity_gco2: float) -> float:
    """Cost of running a load, in major currency units (e.g. pounds).

    cost = energy_kWh * price_per_kWh, with price derived from carbon intensity.
    """
    kwh = power_kw * duration_hours
    pence = kwh * price_p_per_kwh(intensity_gco2)
    return pence / 100.0
