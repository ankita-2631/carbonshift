"""FacilitiesAgent — reduces building energy (Scope 1 + 2)."""
from __future__ import annotations

from ..facilities import optimize_facilities
from .base import Agent, AgentMessage, Blackboard


class FacilitiesAgent(Agent):
    """Recommends efficiency measures for HVAC, lighting, and server rooms."""

    name = "FacilitiesAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        # Value grid electricity at the next 24h average intensity.
        intensity = 250.0
        if bb.forecast is not None:
            intensity = bb.forecast.average_intensity(bb.now, 24.0)

        plan = optimize_facilities(bb.facilities, intensity)
        bb.facility_plan = plan

        summary = (
            f"Reviewed {len(plan.decisions)} facility loads; "
            f"projected saving {plan.total_saved_kg:.1f} kg CO2/day."
        )
        msg = AgentMessage(
            sender=self.name,
            recipient="RiskAgent",
            intent="facilities.proposed",
            summary=summary,
            payload={"loads": len(plan.decisions), "total_saved_kg": round(plan.total_saved_kg, 2)},
        )
        bb.post(msg)
        return [msg]
