"""Travel classifier — the TravelAgent's reasoning about *why* a trip is needed.

For every trip the agent decides two things from the trip's purpose (its name /
description), rather than relying only on pre-set flags:

  - essential: the trip needs physical presence and must NOT be replaced by a video
    call (e.g. a site audit, equipment install, hands-on inspection).
  - relationship_critical: company travel policy prefers in-person contact (e.g. a
    client pitch, investor roadshow, partner relationship), so the trip may switch to a
    cleaner physical mode but should not be silently downgraded to virtual.

Two reasoning paths, mirroring the procurement analyst:
  1. gpt-4o grounded in Foundry IQ (the CarbonShift knowledge base / travel policy).
  2. A transparent keyword heuristic fallback, so the demo still reasons offline.

Any human-set flag on the trip is treated as an authoritative floor: the classifier may
*add* an in-person requirement and always explains its reasoning, but it never downgrades
a trip a human explicitly marked essential or relationship-critical.
"""
from __future__ import annotations

import json
import os
import re

from .knowledge import as_context, retrieve
from .models import Trip

# Cache classifications by trip name so the live dashboard (which re-runs the pipeline
# every poll) pays the LLM cost at most once per unique trip.
_CLASSIFY_CACHE: dict[str, dict] = {}

CLASSIFIER_SYSTEM_PROMPT = """You are CarbonShift's Travel Policy agent. Given a business
trip's purpose, decide whether it must happen in person.

Return two booleans:
- essential: TRUE only if the trip fundamentally requires physical presence and could
  NOT be done as a video call (e.g. a site audit, equipment install/repair, physical
  inspection, lab/fieldwork, hands-on training).
- relationship_critical: TRUE if company travel policy prefers in-person contact for
  relationship reasons (e.g. a client pitch, first client meeting, investor roadshow,
  partner/customer relationship, team off-site, onboarding). Such a trip may use a
  cleaner physical mode but should not be downgraded to virtual.

Rules:
- A routine internal meeting, review, sync, or status update is NEITHER (it can go
  virtual). Prefer the lowest-carbon option unless presence is genuinely needed.
- Ground your judgement in the provided travel-policy knowledge; be conservative.
- rationale: one short sentence explaining the call.
Respond with ONLY a JSON object:
{"essential": bool, "relationship_critical": bool, "rationale": str}
"""

# Transparent keyword fallback. Order matters: an essential match wins over a
# relationship match, which wins over the flexible default.
_ESSENTIAL_KEYWORDS = (
    "audit", "inspection", "inspect", "site visit", "site survey", "survey",
    "install", "installation", "commission", "maintenance", "repair", "on-site",
    "onsite", "factory", "warehouse", "lab", "laboratory", "fieldwork", "field work",
    "site", "physical", "hands-on", "equipment", "construction",
)
_RELATIONSHIP_KEYWORDS = (
    "client", "pitch", "partner", "customer", "investor", "roadshow", "kickoff",
    "kick-off", "first meeting", "off-site", "offsite", "onboarding", "onboard",
    "negotiation", "deal", "relationship", "prospect", "sales", "exec", "board",
)
_FLEXIBLE_KEYWORDS = (
    "review", "sync", "stand-up", "standup", "check-in", "checkin", "1:1", "one-on-one",
    "weekly", "monthly", "quarterly", "internal", "update", "catch-up", "catchup",
    "retro", "planning", "status",
)


def _heuristic_classify(trip: Trip) -> dict:
    """Keyword-based fallback when the LLM is unavailable."""
    text = trip.name.lower()
    essential = any(k in text for k in _ESSENTIAL_KEYWORDS)
    relationship = any(k in text for k in _RELATIONSHIP_KEYWORDS)
    # A flexible signal (e.g. "weekly review") only matters if nothing stronger fired.
    if not essential and not relationship and any(k in text for k in _FLEXIBLE_KEYWORDS):
        return {
            "essential": False,
            "relationship_critical": False,
            "rationale": "Routine internal meeting — can be held as a video call.",
            "citations": ["Travel Policy heuristic"],
        }
    if essential:
        rationale = "Requires physical presence (e.g. site/equipment work), so not virtual."
    elif relationship:
        rationale = "Relationship-critical per travel policy — prefer in person, cleaner mode."
    else:
        rationale = "No in-person requirement detected — lowest-carbon mode is viable."
    return {
        "essential": essential,
        "relationship_critical": relationship,
        "rationale": rationale,
        "citations": ["Travel Policy heuristic"],
    }


def _llm_classify(trip: Trip) -> dict | None:
    """Ask gpt-4o (grounded in Foundry IQ) to classify the trip. None on failure."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    deployment = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o")
    if not endpoint:
        return None
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        snippets = retrieve(
            f"business travel policy in-person requirement for {trip.name}"
        )
        client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        openai_client = client.get_openai_client()
        user_content = (
            f"Trip purpose: {trip.name}\n"
            f"One-way distance: {trip.distance_km:.0f} km\n"
            f"Passengers: {trip.passengers}\n\n"
            f"Travel-policy knowledge:\n{as_context(snippets)}"
        )
        response = openai_client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
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


def classify_trip(trip: Trip) -> dict:
    """Classify a trip's in-person need: LLM first, heuristic fallback. Cached by name.

    Returns a dict with keys: essential, relationship_critical, rationale, citations.
    """
    key = trip.name
    if key in _CLASSIFY_CACHE:
        return _CLASSIFY_CACHE[key]
    result = _llm_classify(trip) or _heuristic_classify(trip)
    result.setdefault("essential", False)
    result.setdefault("relationship_critical", False)
    result.setdefault("rationale", "")
    result.setdefault("citations", [])
    _CLASSIFY_CACHE[key] = result
    return result
