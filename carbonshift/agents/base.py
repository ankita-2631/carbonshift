"""Multi-agent core: shared blackboard, inter-agent messages, and the base Agent.

CarbonShift uses a small team of specialised agents that collaborate on a shared
"blackboard" and communicate by passing typed messages on a bus:

    ForecastAgent -> OptimizerAgent -> TravelAgent -> RiskAgent -> CostAgent -> BriefingAgent

Each agent reads the current blackboard state, does its job, writes its results back,
and emits one or more messages addressed to the next agent. The orchestrator records
the full transcript so the conversation between agents is visible in the demo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..carbon_data import CarbonForecast
from ..models import (
    Job,
    MeasurePlan,
    PurchaseLine,
    SchedulePlan,
    Trip,
    TravelPlan,
    Vehicle,
)


@dataclass
class AgentMessage:
    """A single message passed from one agent to another."""

    sender: str
    recipient: str
    intent: str          # short verb-phrase, e.g. "forecast.ready"
    summary: str         # human-readable one-liner for the transcript
    payload: dict = field(default_factory=dict)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"{self.sender} -> {self.recipient} [{self.intent}]: {self.summary}"


@dataclass
class RevisionRequest:
    """A RiskAgent ask for a specific agent to re-plan under tighter constraints."""

    target: str          # name of the agent that must revise (e.g. "OptimizerAgent")
    reason: str          # human-readable critique for the transcript
    constraints: dict = field(default_factory=dict)  # e.g. {"safety_buffer_hours": 0.75}


@dataclass
class Blackboard:
    """Shared working memory all agents read from and write to."""

    now: datetime
    jobs: list[Job]
    job_source: str = ""    # where the jobs came from (org scheduler or demo)
    trips: list[Trip] = field(default_factory=list)
    trip_source: str = ""   # where the trips came from (org travel app or demo)
    vehicles: list[Vehicle] = field(default_factory=list)
    purchases: list[PurchaseLine] = field(default_factory=list)

    # Demo control: gCO2/kWh added to the near-term grid forecast to simulate a
    # grid stress event so the agents visibly re-plan. 0 = use the real forecast.
    grid_spike: float = 0.0

    # Produced by ForecastAgent.
    forecast: CarbonForecast | None = None
    forecast_confidence: float = 0.0   # 0..1

    # Produced by OptimizerAgent.
    plan: SchedulePlan | None = None

    # Produced by TravelAgent.
    travel_plan: TravelPlan | None = None

    # Produced by FleetAgent / ProcurementAgent.
    fleet_plan: MeasurePlan | None = None
    procurement_plan: MeasurePlan | None = None

    # Produced by RiskAgent.
    risk_verdict: str = ""
    risk_ok: bool = True
    risk_counts: dict = field(default_factory=dict)
    safety_violations: list[str] = field(default_factory=list)

    # Negotiation state: RiskAgent can send work back to a proposer to re-plan.
    revision_requests: list["RevisionRequest"] = field(default_factory=list)
    applied_safety_buffer_hours: float = 0.0
    keep_physical_trips: list[str] = field(default_factory=list)
    negotiation_rounds: int = 0

    # Produced by CostAgent (org-wide roll-up across all domains).
    total_kg_saved: float = 0.0
    total_money_saved: float = 0.0
    cost_summary: str = ""

    # Produced by BriefingAgent.
    briefing: str = ""

    # Conversation transcript across all agents.
    transcript: list[AgentMessage] = field(default_factory=list)

    def post(self, message: AgentMessage) -> None:
        self.transcript.append(message)


class Agent:
    """Base class for a CarbonShift agent."""

    name: str = "agent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        """Do this agent's work against the blackboard and return emitted messages."""
        raise NotImplementedError

    def revise(self, bb: Blackboard, request: "RevisionRequest") -> list[AgentMessage]:
        """Re-plan in response to a RiskAgent critique. Defaults to re-running process."""
        return self.process(bb)
