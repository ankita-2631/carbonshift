"""CostAgent — rolls up CO2 and money saved across every domain.

Different domains save on different cadences (compute jobs run nightly, travel repeats
~monthly, fleet and procurement savings are annual). To produce one honest, comparable
headline, this agent annualises each domain using explicit, transparent assumptions and
reports an *estimated annual* impact. The native per-cycle figures remain visible in the
detail sections.
"""
from __future__ import annotations

from ..pricing import CURRENCY_SYMBOL
from .base import Agent, AgentMessage, Blackboard

# Annualisation assumptions (made explicit so the headline is auditable).
COMPUTE_RUNS_PER_YEAR = 365      # batch/charging jobs assumed to recur nightly
TRAVEL_CYCLES_PER_YEAR = 12      # the planned trip set assumed to repeat ~monthly
# Fleet and procurement plans are already expressed as annual figures (factor = 1).


class CostAgent(Agent):
    """Annualises and aggregates carbon and cost savings across all four domains."""

    name = "CostAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        annual_kg = 0.0
        annual_money = 0.0

        if bb.plan is not None:
            annual_kg += bb.plan.total_saved_kg * COMPUTE_RUNS_PER_YEAR
            annual_money += bb.plan.total_money_saved * COMPUTE_RUNS_PER_YEAR
        if bb.travel_plan is not None:
            annual_kg += bb.travel_plan.total_saved_kg * TRAVEL_CYCLES_PER_YEAR
            annual_money += bb.travel_plan.total_money_saved * TRAVEL_CYCLES_PER_YEAR
        if bb.fleet_plan is not None:
            annual_kg += bb.fleet_plan.total_saved_kg
            annual_money += bb.fleet_plan.total_money_saved
        if bb.procurement_plan is not None:
            annual_kg += bb.procurement_plan.total_saved_kg
            annual_money += bb.procurement_plan.total_money_saved

        bb.total_kg_saved = annual_kg
        bb.total_money_saved = annual_money
        bb.cost_summary = (
            f"Estimated annual impact: {annual_kg / 1000.0:.1f} tonnes CO2 avoided and "
            f"{CURRENCY_SYMBOL}{annual_money:,.0f} saved across compute, travel, "
            f"fleet, and procurement."
        )

        msg = AgentMessage(
            sender=self.name,
            recipient="BriefingAgent",
            intent="savings.rollup",
            summary=bb.cost_summary,
            payload={
                "annual_kg_saved": round(annual_kg, 2),
                "annual_money_saved": round(annual_money, 2),
                "currency": CURRENCY_SYMBOL,
                "assumptions": {
                    "compute_runs_per_year": COMPUTE_RUNS_PER_YEAR,
                    "travel_cycles_per_year": TRAVEL_CYCLES_PER_YEAR,
                },
            },
        )
        bb.post(msg)
        return [msg]
