"""OptimizerAgent — chooses the lowest-carbon start window for each job."""
from __future__ import annotations

from ..scheduler import optimize_plan
from .base import Agent, AgentMessage, Blackboard, RevisionRequest


class OptimizerAgent(Agent):
    """Runs the deterministic optimizer over all jobs using the forecast."""

    name = "OptimizerAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        if bb.forecast is None:
            raise RuntimeError("OptimizerAgent ran before a forecast was available.")
        return self._optimize(bb, buffer_hours=bb.applied_safety_buffer_hours)

    def revise(self, bb: Blackboard, request: RevisionRequest) -> list[AgentMessage]:
        """Re-plan with the extra deadline headroom the RiskAgent asked for."""
        buffer = float(request.constraints.get("safety_buffer_hours", 0.0))
        bb.applied_safety_buffer_hours = buffer
        return self._optimize(bb, buffer_hours=buffer, revised=True, reason=request.reason)

    def _optimize(
        self,
        bb: Blackboard,
        buffer_hours: float = 0.0,
        revised: bool = False,
        reason: str = "",
    ) -> list[AgentMessage]:
        plan = optimize_plan(
            bb.jobs, bb.forecast, now=bb.now, safety_buffer_hours=buffer_hours
        )
        bb.plan = plan

        shifted = sum(1 for d in plan.decisions if d.chosen_start != d.baseline_start)
        if revised:
            summary = (
                f"Re-planned with a {buffer_hours * 60:.0f}-min safety buffer "
                f"({reason}). Shifted {shifted}; revised saving "
                f"{plan.total_saved_kg:.1f} kg CO2 ({plan.total_pct_saved:.0f}%)."
            )
            intent = "plan.revised"
        else:
            summary = (
                f"Optimised {len(plan.decisions)} jobs; shifted {shifted}. "
                f"Projected saving {plan.total_saved_kg:.1f} kg CO2 "
                f"({plan.total_pct_saved:.0f}%)."
            )
            intent = "plan.proposed"
        msg = AgentMessage(
            sender=self.name,
            recipient="RiskAgent",
            intent=intent,
            summary=summary,
            payload={
                "jobs": len(plan.decisions),
                "shifted": shifted,
                "total_saved_kg": round(plan.total_saved_kg, 2),
                "safety_buffer_hours": buffer_hours,
            },
        )
        bb.post(msg)
        return [msg]
