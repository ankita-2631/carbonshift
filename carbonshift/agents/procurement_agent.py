"""ProcurementAgent — switches purchases to lower-carbon alternatives (Scope 3)."""
from __future__ import annotations

from ..procurement import optimize_procurement
from .base import Agent, AgentMessage, Blackboard


class ProcurementAgent(Agent):
    """Recommends lower-carbon suppliers/materials for purchased goods & services."""

    name = "ProcurementAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        plan = optimize_procurement(bb.purchases)
        bb.procurement_plan = plan

        changed = sum(1 for d in plan.decisions if d.kg_co2_saved > 0)
        ai_count = sum(1 for d in plan.decisions if d.ai_proposed)
        ai_note = f" Independently selected greener options for {ai_count} new item(s) via Foundry IQ." if ai_count else ""
        summary = (
            f"Reviewed {len(plan.decisions)} purchase lines; recommended switching {changed}. "
            f"Projected saving {plan.total_saved_kg:.0f} kg CO2e.{ai_note}"
        )
        msg = AgentMessage(
            sender=self.name,
            recipient="RiskAgent",
            intent="procurement.proposed",
            summary=summary,
            payload={"lines": len(plan.decisions), "switched": changed,
                     "ai_analysed": ai_count,
                     "total_saved_kg": round(plan.total_saved_kg, 2)},
        )
        bb.post(msg)
        return [msg]
