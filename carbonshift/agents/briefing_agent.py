"""BriefingAgent — the only LLM agent; writes the grounded operator briefing.

Consumes the optimizer's plan plus the RiskAgent's safety verdict and the
ForecastAgent's confidence, then asks gpt-4o (grounded by Foundry IQ) to produce a
clear, cited briefing. Falls back to a deterministic local template when Foundry is
not configured, so the demo always runs.
"""
from __future__ import annotations

import os

from ..models import MeasurePlan, SchedulePlan, TravelPlan
from ..pricing import CURRENCY_SYMBOL
from .base import Agent, AgentMessage, Blackboard

SYSTEM_PROMPT = """You are CarbonShift's Briefing Agent for an organization's
sustainability co-pilot. You receive decisions across four domains: (1) compute
scheduling, (2) business travel, (3) vehicle fleet, and (4) procurement; plus a safety
verdict from a Risk Agent, a forecast-confidence score, and an org-wide roll-up of CO2
and money saved. Write a concise briefing for an operations or sustainability lead.

Rules:
- NEVER change a decision or claim a saving the data does not support.
- If the Risk Agent reports a BLOCKED verdict, lead with the safety problem and do
  NOT recommend applying the plan.
- Lead with the headline: total CO2 avoided AND total money saved.
- For compute, state kg CO2 saved and confirm deadlines are honoured.
- For travel, state the recommended mode change and CO2/money saved; never send an
  essential trip virtual.
- For fleet and procurement, state the recommended action and the CO2 and
  money it saves; flag any item that cannot be changed.
- Ground factual claims about grid intensity or emission factors in the knowledge base
  and cite it.
- Mention forecast confidence. Be concise. This is decision support, not a guarantee.
"""


def _plan_as_facts(plan: SchedulePlan) -> str:
    rows = []
    for d in plan.decisions:
        rows.append(
            f"- {d.job.name}: chosen_start={d.chosen_start.isoformat()}, "
            f"baseline_start={d.baseline_start.isoformat()}, "
            f"chosen_intensity={d.chosen_intensity:.0f} gCO2/kWh, "
            f"baseline_intensity={d.baseline_intensity:.0f} gCO2/kWh, "
            f"kg_saved={d.kg_co2_saved:.2f}, money_saved={d.money_saved:.2f}, "
            f"pct_saved={d.pct_saved:.0f}, "
            f"deadline={d.job.deadline.isoformat()}, risk={d.risk.value}"
        )
    return "\n".join(rows)


def _travel_as_facts(plan: TravelPlan) -> str:
    rows = []
    for d in plan.decisions:
        rows.append(
            f"- {d.trip.name}: baseline_mode={d.baseline_mode.value}, "
            f"chosen_mode={d.chosen_mode.value}, "
            f"kg_saved={d.kg_co2_saved:.2f}, money_saved={d.money_saved:.2f}, "
            f"essential={d.trip.essential}, risk={d.risk.value}"
        )
    return "\n".join(rows)


def _measures_as_facts(plan: MeasurePlan) -> str:
    rows = []
    for d in plan.decisions:
        rows.append(
            f"- {d.name}: action={d.action}, kg_saved={d.kg_co2_saved:.2f}, "
            f"money_saved={d.money_saved:.2f}, pct_saved={d.pct_saved:.0f}, "
            f"risk={d.risk.value}"
        )
    return "\n".join(rows) if rows else "none"


def _local_briefing(bb: Blackboard) -> str:
    plan = bb.plan
    lines = [
        f"CarbonShift org plan: {bb.cost_summary} "
        f"Forecast confidence {bb.forecast_confidence:.0%}.",
        f"Risk Agent: {bb.risk_verdict}",
        "",
        "Compute workloads:",
    ]
    for d in plan.decisions:
        lines.append(
            f"[{d.risk.value.upper()}] {d.job.name}: start {d.chosen_start:%a %H:%M} UTC "
            f"(was {d.baseline_start:%a %H:%M}) -> {d.kg_co2_saved:.1f} kg, "
            f"{CURRENCY_SYMBOL}{d.money_saved:.0f} saved. {d.rationale}"
        )
    if bb.travel_plan and bb.travel_plan.decisions:
        lines.append("")
        lines.append("Business travel:")
        for t in bb.travel_plan.decisions:
            lines.append(
                f"[{t.risk.value.upper()}] {t.trip.name}: {t.baseline_mode.value} -> "
                f"{t.chosen_mode.value} -> {t.kg_co2_saved:.1f} kg, "
                f"{CURRENCY_SYMBOL}{t.money_saved:.0f} saved. {t.rationale}"
            )
    for title, mplan in (
        ("Fleet", bb.fleet_plan),
        ("Procurement", bb.procurement_plan),
    ):
        if mplan and mplan.decisions:
            lines.append("")
            lines.append(f"{title}:")
            for m in mplan.decisions:
                lines.append(
                    f"[{m.risk.value.upper()}] {m.name}: {m.action} -> "
                    f"{m.kg_co2_saved:.1f} kg, {CURRENCY_SYMBOL}{m.money_saved:.0f} saved. "
                    f"{m.rationale}"
                )
    lines.append("")
    lines.append(
        "Note: estimates depend on third-party grid forecasts and emission factors; "
        "deadlines are always honoured."
    )
    return "\n".join(lines)


class BriefingAgent(Agent):
    """Turns the validated plan into a grounded, cited natural-language briefing."""

    name = "BriefingAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        if bb.plan is None:
            raise RuntimeError("BriefingAgent ran before a plan was available.")

        bb.briefing = self._write(bb)
        msg = AgentMessage(
            sender=self.name,
            recipient="user",
            intent="briefing.final",
            summary=f"Briefing ready (est. annual {bb.total_kg_saved / 1000.0:.1f} t CO2, "
            f"{CURRENCY_SYMBOL}{bb.total_money_saved:,.0f} saved).",
            payload={"approved": bb.risk_ok},
        )
        bb.post(msg)
        return [msg]

    def _write(self, bb: Blackboard) -> str:
        endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        deployment = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o")
        if not endpoint:
            return _local_briefing(bb)

        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
            openai_client = client.get_openai_client()
            travel_facts = (
                _travel_as_facts(bb.travel_plan)
                if bb.travel_plan and bb.travel_plan.decisions
                else "none"
            )
            user_content = (
                f"Forecast confidence: {bb.forecast_confidence:.0%}\n"
                f"Risk Agent verdict: {bb.risk_verdict}\n"
                f"Safety violations: {bb.safety_violations or 'none'}\n"
                f"Org-wide roll-up: {bb.total_kg_saved:.1f} kg CO2 and "
                f"{CURRENCY_SYMBOL}{bb.total_money_saved:.0f} saved\n\n"
                "Compute decisions:\n" + _plan_as_facts(bb.plan) + "\n\n"
                "Travel decisions:\n" + travel_facts + "\n\n"
                "Fleet decisions:\n"
                + (_measures_as_facts(bb.fleet_plan) if bb.fleet_plan else "none")
                + "\n\nProcurement decisions:\n"
                + (_measures_as_facts(bb.procurement_plan) if bb.procurement_plan else "none")
            )
            response = openai_client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content or _local_briefing(bb)
        except Exception as exc:  # pragma: no cover - network/SDK variance
            return _local_briefing(bb) + f"\n\n(Foundry unavailable: {exc})"
