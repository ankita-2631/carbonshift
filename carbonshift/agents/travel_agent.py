"""TravelAgent — optimises business trips for lower CO2 and cost."""
from __future__ import annotations

from ..travel import optimize_travel
from .base import Agent, AgentMessage, Blackboard, RevisionRequest


class TravelAgent(Agent):
    """Recommends the cleanest viable travel mode for each trip."""

    name = "TravelAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        return self._optimize(bb, keep_physical=set(bb.keep_physical_trips))

    def revise(self, bb: Blackboard, request: RevisionRequest) -> list[AgentMessage]:
        """Re-plan, keeping the RiskAgent's flagged trips in a physical mode."""
        trips = set(request.constraints.get("keep_physical", []))
        bb.keep_physical_trips = sorted(set(bb.keep_physical_trips) | trips)
        return self._optimize(
            bb, keep_physical=set(bb.keep_physical_trips), revised=True,
            reason=request.reason,
        )

    def _optimize(
        self,
        bb: Blackboard,
        keep_physical: set[str] | None = None,
        revised: bool = False,
        reason: str = "",
    ) -> list[AgentMessage]:
        plan = optimize_travel(bb.trips, keep_physical=keep_physical)
        bb.travel_plan = plan

        changed = sum(1 for d in plan.decisions if d.chosen_mode != d.baseline_mode)
        in_person = sum(
            1 for d in plan.decisions
            if d.trip.essential or d.trip.relationship_critical
        )
        if revised:
            summary = (
                f"Re-planned travel to keep {len(keep_physical or [])} relationship-critical "
                f"trip(s) in person ({reason}). Now changing {changed}; "
                f"saving {plan.total_saved_kg:.1f} kg CO2."
            )
            intent = "travel.revised"
        else:
            class_note = (
                f" Classified in-person need for all {len(plan.decisions)} trip(s) via "
                f"Foundry IQ ({in_person} require presence)."
                if plan.decisions else ""
            )
            summary = (
                f"Reviewed {len(plan.decisions)} trips; recommended a change for {changed}. "
                f"Projected saving {plan.total_saved_kg:.1f} kg CO2.{class_note}"
            )
            intent = "travel.proposed"
        msg = AgentMessage(
            sender=self.name,
            recipient="RiskAgent",
            intent=intent,
            summary=summary,
            payload={
                "trips": len(plan.decisions),
                "changed": changed,
                "total_saved_kg": round(plan.total_saved_kg, 2),
            },
        )
        bb.post(msg)
        return [msg]
