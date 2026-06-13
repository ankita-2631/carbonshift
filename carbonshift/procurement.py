"""Procurement optimizer (Scope 3).

Compares each purchased good/service against a lower-carbon alternative, accounting for
any cost difference.

Two reasoning paths:
  1. Known item  — the line ships with a vetted `alt_reduction_pct`; we apply
     transparent deterministic trade-off math (carbon cut vs. cost change).
  2. New / unknown item (`alt_reduction_pct is None`, not locked) — the agent reasons
     about the best lower-carbon alternative itself, using gpt-4o grounded in Foundry IQ
     (the CarbonShift knowledge base), then selects and acts on it under the *same*
     merit criteria as a known item. The choice is flagged as agent-selected and cites
     its sources, so the decision is transparent — but the agent makes the call.

Embodied-carbon figures are transparent estimates, not a live feed.
"""
from __future__ import annotations

import json
import os
import re

from .knowledge import as_context, retrieve
from .models import MeasureDecision, MeasurePlan, PurchaseLine, RiskLevel

GREEN_THRESHOLD_PCT = 15.0

# Cache agent analyses by item signature so the live dashboard (which re-runs the
# pipeline every poll) pays the LLM cost at most once per unique unknown item.
_PROPOSAL_CACHE: dict[tuple, dict] = {}

ANALYST_SYSTEM_PROMPT = """You are CarbonShift's Procurement Analyst agent. Given a
purchased good/service, propose the single best lower-carbon alternative for it.

Rules:
- Ground your reduction and cost estimates in the provided knowledge base; do not invent
  figures that contradict it. Prefer conservative estimates.
- reduction_pct is the FRACTION of embodied carbon avoided (0.0-1.0).
- cost_delta_pct is the fractional change in spend (-0.10 = 10% cheaper, 0.05 = 5% more).
- If no credible lower-carbon alternative exists, set alternative to "" and reduction_pct to 0.
Respond with ONLY a JSON object:
{"alternative": str, "reduction_pct": float, "cost_delta_pct": float, "rationale": str}
"""

# Conservative offline fallback ranges (grounded in the Sustainability Reference Data
# doc) so the agent still "takes action" on a new item when Foundry is not configured.
_HEURISTICS = (
    (("paper", "stationery", "print"), 0.40, -0.05, "recycled-content alternative"),
    (("laptop", "computer", "device", "hardware", "electronic", "monitor", "phone"),
     0.30, 0.0, "refurbished / extended-life devices"),
    (("packaging", "box", "carton", "wrap"), 0.35, 0.03, "recycled/compostable packaging"),
    (("merch", "apparel", "textile", "cotton", "tote", "garment", "clothing"),
     0.30, 0.05, "organic/recycled-textile alternative"),
    (("furniture", "fit-out", "chair", "desk"), 0.25, 0.0, "refurbished/remanufactured option"),
    (("cloud", "storage", "compute", "hosting", "data"), 0.20, 0.0,
     "right-sized / greener-region provisioning"),
)


def _heuristic_proposal(line: PurchaseLine) -> dict:
    """Category-based fallback estimate when the LLM is unavailable."""
    text = line.name.lower()
    for keywords, reduction, cost_delta, alt in _HEURISTICS:
        if any(k in text for k in keywords):
            return {
                "alternative": alt,
                "reduction_pct": reduction,
                "cost_delta_pct": cost_delta,
                "rationale": (
                    f"Category heuristic (pending detailed analysis): a {alt} typically "
                    f"avoids ~{reduction * 100:.0f}% of embodied carbon."
                ),
                "citations": ["Sustainability Reference Data"],
            }
    return {
        "alternative": "",
        "reduction_pct": 0.0,
        "cost_delta_pct": 0.0,
        "rationale": "No category match found; flagged for procurement review.",
        "citations": [],
    }


def _llm_proposal(line: PurchaseLine) -> dict | None:
    """Ask gpt-4o (grounded in Foundry IQ) for the best alternative. None on failure."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    deployment = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o")
    if not endpoint:
        return None
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        snippets = retrieve(f"lower-carbon alternative for {line.name} procurement Scope 3")
        client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        openai_client = client.get_openai_client()
        user_content = (
            f"Item: {line.name}\n"
            f"Current embodied carbon: {line.kg_co2e:.0f} kg CO2e\n"
            f"Current annual spend: {line.cost:.0f}\n\n"
            f"Knowledge base context:\n{as_context(snippets)}"
        )
        response = openai_client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        data["citations"] = [s for _c, s in snippets] or ["Foundry IQ"]
        return data
    except Exception:
        return None


def _analyse_unknown(line: PurchaseLine) -> dict:
    """Agentic reasoning for a new item: LLM first, heuristic fallback. Cached."""
    key = (line.name, round(line.kg_co2e, 1), round(line.cost, 1))
    if key in _PROPOSAL_CACHE:
        return _PROPOSAL_CACHE[key]
    proposal = _llm_proposal(line) or _heuristic_proposal(line)
    _PROPOSAL_CACHE[key] = proposal
    return proposal


def optimize_purchase(line: PurchaseLine) -> MeasureDecision:
    base_kg = line.kg_co2e
    base_cost = line.cost

    # Locked: contractual / single-source — cannot switch.
    if line.locked:
        return MeasureDecision(
            name=line.name, domain="procurement",
            action="Keep current supplier (single-source / contractual)",
            kg_co2_baseline=base_kg, kg_co2_chosen=base_kg,
            cost_baseline=base_cost, cost_chosen=base_cost,
            risk=RiskLevel.RED,
            rationale="No switchable lower-carbon alternative is currently available.",
        )

    # New / unknown item: the agent reasons about the best alternative itself.
    ai_proposed = False
    citations: list[str] = []
    if line.alt_reduction_pct is None:
        proposal = _analyse_unknown(line)
        reduction = max(0.0, min(1.0, float(proposal.get("reduction_pct", 0.0))))
        cost_delta = float(proposal.get("cost_delta_pct", 0.0))
        alternative = proposal.get("alternative") or ""
        citations = proposal.get("citations", [])
        ai_proposed = True
        if reduction <= 0 or not alternative:
            return MeasureDecision(
                name=line.name, domain="procurement",
                action="Flag for procurement review (no clear greener option found)",
                kg_co2_baseline=base_kg, kg_co2_chosen=base_kg,
                cost_baseline=base_cost, cost_chosen=base_cost,
                risk=RiskLevel.RED,
                rationale=proposal.get("rationale", "No alternative identified."),
                citations=citations, ai_proposed=True,
            )
    else:
        reduction = max(0.0, min(1.0, line.alt_reduction_pct))
        cost_delta = line.alt_cost_delta_pct
        alternative = line.alternative
        if reduction <= 0:
            return MeasureDecision(
                name=line.name, domain="procurement",
                action="Keep current supplier (no lower-carbon alternative)",
                kg_co2_baseline=base_kg, kg_co2_chosen=base_kg,
                cost_baseline=base_cost, cost_chosen=base_cost,
                risk=RiskLevel.RED,
                rationale="No switchable lower-carbon alternative is currently available.",
            )

    chosen_kg = base_kg * (1.0 - reduction)
    chosen_cost = base_cost * (1.0 + cost_delta)
    pct = reduction * 100.0
    cheaper_or_neutral = cost_delta <= 0.02  # within 2% counts as neutral

    # The agent rates every switch on the same merit: a meaningful, cost-neutral cut is
    # GREEN whether the option was pre-vetted or selected by the agent itself.
    if pct >= GREEN_THRESHOLD_PCT and cheaper_or_neutral:
        risk = RiskLevel.GREEN
    else:
        risk = RiskLevel.AMBER

    cost_note = (
        "at no extra cost" if cost_delta <= 0
        else f"for ~{cost_delta * 100:.0f}% more spend"
    )
    prefix = "Agent-selected: " if ai_proposed else ""
    rationale = (
        f"{prefix}switching to {alternative} cuts embodied carbon by {pct:.0f}% "
        f"({base_kg:.0f} → {chosen_kg:.0f} kg CO2e) {cost_note}."
    )
    return MeasureDecision(
        name=line.name,
        domain="procurement",
        action=f"Switch to {alternative}",
        kg_co2_baseline=base_kg,
        kg_co2_chosen=chosen_kg,
        cost_baseline=base_cost,
        cost_chosen=chosen_cost,
        risk=risk,
        rationale=rationale,
        citations=citations,
        ai_proposed=ai_proposed,
    )


def optimize_procurement(lines: list[PurchaseLine]) -> MeasurePlan:
    plan = MeasurePlan(domain="procurement")
    for line in lines:
        plan.decisions.append(optimize_purchase(line))
    return plan
