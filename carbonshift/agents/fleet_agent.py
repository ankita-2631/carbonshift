"""FleetAgent — electrifies vehicles and logistics routes (Scope 1 + 3)."""
from __future__ import annotations

from ..fleet import optimize_fleet
from .base import Agent, AgentMessage, Blackboard


class FleetAgent(Agent):
    """Recommends electrifying owned vehicles, logistics, and grey-fleet commuting."""

    name = "FleetAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        plan = optimize_fleet(bb.vehicles)
        bb.fleet_plan = plan

        changed = sum(1 for d in plan.decisions if d.kg_co2_saved > 0)
        blocked = sum(
            1 for d in plan.decisions
            if d.kg_co2_saved <= 0 and "deploy charging" in d.action
        )
        charge_note = (
            f" {blocked} route(s) await charging infrastructure before switching."
            if blocked else ""
        )
        summary = (
            f"Routed {len(plan.decisions)} vehicles against EV range + charging "
            f"availability; recommended electrifying {changed}. "
            f"Projected saving {plan.total_saved_kg:.0f} kg CO2/yr.{charge_note}"
        )
        msg = AgentMessage(
            sender=self.name,
            recipient="RiskAgent",
            intent="fleet.proposed",
            summary=summary,
            payload={"vehicles": len(plan.decisions), "electrified": changed,
                     "charging_blocked": blocked,
                     "total_saved_kg": round(plan.total_saved_kg, 2)},
        )
        bb.post(msg)
        return [msg]
