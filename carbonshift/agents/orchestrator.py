"""Orchestrator — runs the CarbonShift agent team as a negotiation loop.

Pipeline:
    ForecastAgent -> OptimizerAgent -> TravelAgent -> FleetAgent
    -> ProcurementAgent -> RiskAgent -> CostAgent -> BriefingAgent

This is not a single linear pass. The proposer agents put plans on the shared
blackboard; the RiskAgent reviews them and may send work *back* to a proposer with a
critique (e.g. "this job finishes too close to its deadline — re-plan with a buffer").
The orchestrator dispatches those revision requests and re-reviews until the RiskAgent
is satisfied or a round limit is reached. Only then do the finaliser agents run.
The full back-and-forth is recorded in the transcript.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import Facility, Job, PurchaseLine, Trip, Vehicle
from .base import Agent, Blackboard
from .briefing_agent import BriefingAgent
from .cost_agent import CostAgent
from .fleet_agent import FleetAgent
from .forecast_agent import ForecastAgent
from .optimizer_agent import OptimizerAgent
from .procurement_agent import ProcurementAgent
from .risk_agent import RiskAgent
from .travel_agent import TravelAgent

# How many times the RiskAgent may send work back before we accept the plan as-is.
MAX_NEGOTIATION_ROUNDS = 3


class Orchestrator:
    """Coordinates the agent team over a shared blackboard with a review loop."""

    REVIEWER = "RiskAgent"

    def __init__(self, agents: list[Agent] | None = None):
        self.agents: list[Agent] = agents or [
            ForecastAgent(),
            OptimizerAgent(),
            TravelAgent(),
            FleetAgent(),
            ProcurementAgent(),
            RiskAgent(),
            CostAgent(),
            BriefingAgent(),
        ]

    def run(
        self,
        jobs: list[Job],
        trips: list[Trip] | None = None,
        now: datetime | None = None,
        trip_source: str = "",
        job_source: str = "",
        facilities: list[Facility] | None = None,
        vehicles: list[Vehicle] | None = None,
        purchases: list[PurchaseLine] | None = None,
        grid_spike: float = 0.0,
    ) -> Blackboard:
        bb = Blackboard(
            now=now or datetime.now(timezone.utc),
            jobs=jobs,
            job_source=job_source,
            trips=trips or [],
            trip_source=trip_source,
            facilities=facilities or [],
            vehicles=vehicles or [],
            purchases=purchases or [],
            grid_spike=grid_spike,
        )

        # Split the team into proposers (before the reviewer), the reviewer, and
        # finalisers (after the reviewer) so the loop works for any agent list.
        registry = {a.name: a for a in self.agents}
        reviewer = registry.get(self.REVIEWER)
        names = [a.name for a in self.agents]
        split = names.index(self.REVIEWER) if self.REVIEWER in names else len(self.agents)
        proposers = self.agents[:split]
        finalisers = self.agents[split + 1:]

        # 1) Proposers put their initial plans on the blackboard.
        for agent in proposers:
            agent.process(bb)

        # 2) Review/revise loop: the reviewer critiques and may send work back.
        if reviewer is not None:
            for _ in range(MAX_NEGOTIATION_ROUNDS):
                reviewer.process(bb)
                if not bb.revision_requests:
                    break
                bb.negotiation_rounds += 1
                for request in bb.revision_requests:
                    target = registry.get(request.target)
                    if target is not None:
                        target.revise(bb, request)
                bb.revision_requests = []
            else:
                # Ran out of rounds with requests still pending: do a final clean
                # review so the verdict reflects the last accepted plan.
                bb.revision_requests = []
                reviewer.process(bb)

        # 3) Finalisers roll up and brief on the approved plan.
        for agent in finalisers:
            agent.process(bb)
        return bb
