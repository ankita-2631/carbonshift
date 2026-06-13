"""CarbonShift multi-agent system.

A team of specialised agents collaborates over a shared blackboard:
    ForecastAgent -> OptimizerAgent -> TravelAgent -> FleetAgent
    -> ProcurementAgent -> RiskAgent -> CostAgent -> BriefingAgent
"""
from .base import Agent, AgentMessage, Blackboard, RevisionRequest
from .briefing_agent import BriefingAgent
from .cost_agent import CostAgent
from .fleet_agent import FleetAgent
from .forecast_agent import ForecastAgent
from .optimizer_agent import OptimizerAgent
from .orchestrator import Orchestrator
from .procurement_agent import ProcurementAgent
from .risk_agent import RiskAgent
from .travel_agent import TravelAgent

__all__ = [
    "Agent",
    "AgentMessage",
    "Blackboard",
    "RevisionRequest",
    "Orchestrator",
    "ForecastAgent",
    "OptimizerAgent",
    "TravelAgent",
    "FleetAgent",
    "ProcurementAgent",
    "RiskAgent",
    "CostAgent",
    "BriefingAgent",
]
