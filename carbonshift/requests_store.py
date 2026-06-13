"""Unified request store (all domains).

The team dashboard is operated by the carbon-reduction team — staff never touch it.
Instead anyone can submit a request through a small portal covering every domain:

* **Compute workload** — a manual request to run a deferrable job; the OptimizerAgent
  reasoning shifts it into the greenest grid window (or runs it now if overridden).
* **Business travel** — a trip request; the TravelAgent reasons about in-person need
  and recommends rail or a virtual meeting.
* **Fleet** — mostly automatic from delivery/courier telematics; this is the manual
  path to add a vehicle/route, which the FleetAgent assesses for electrification.
* **Procurement** — a purchased good/service; the ProcurementAgent proposes a
  lower-carbon alternative (embodied carbon estimated from spend when not supplied).

The same agent reasoning that powers the dashboard runs on each request, and the
requester receives an email-style response with the recommendation plus *Accept* /
*Override* actions.

* **Accept**  — follow the greener recommendation. The item flows onto the team
  dashboard with its ✦ AI marker.
* **Override** — keep the original, carbon-heavier choice for a stated reason. The
  item is forced to stay as requested and is flagged on the team dashboard with a
  ⚑ Override badge plus the reason, so the team has full visibility.

Requests persist to ``manager_requests.json`` (project root, override with
``MANAGER_REQUESTS_PATH``); a copy of each outbound email is written to
``manager_emails/`` as a standards-compliant ``.eml`` file (no SMTP needed for a demo).
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

from .carbon_data import get_forecast
from .emission_factors import estimate_embodied_kg
from .fleet import optimize_vehicle
from .models import FuelType, Job, PurchaseLine, TravelMode, Trip, Vehicle
from .procurement import optimize_purchase
from .scheduler import optimize_job
from .travel import optimize_trip

DOMAINS = ("compute", "travel", "fleet", "procurement")

FROM_ADDRESS = "carbonshift-copilot@contoso.com"
SERVER_BASE = os.environ.get("CARBONSHIFT_BASE_URL", "http://127.0.0.1:5000")


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _store_path() -> str:
    return os.environ.get("MANAGER_REQUESTS_PATH") or os.path.join(
        _root(), "manager_requests.json"
    )


def _emails_dir() -> str:
    d = os.path.join(_root(), "manager_emails")
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _load() -> list[dict]:
    try:
        with open(_store_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(records: list[dict]) -> None:
    with open(_store_path(), "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)


def store_version() -> str:
    """Cheap fingerprint so the dashboard can detect manager decisions and re-render."""
    try:
        st = os.stat(_store_path())
        return f"{int(st.st_size)}-{int(st.st_mtime)}"
    except OSError:
        return "0"


def all_requests() -> list[dict]:
    return _load()


def get_request(rid: str) -> dict | None:
    return next((r for r in _load() if r["id"] == rid), None)


# --------------------------------------------------------------------------- #
# Submit + decide
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Per-domain reasoning: build the input object, run the agent optimizer, and
# return a normalised ``rec`` dict the email/preview/dashboard all share.
# --------------------------------------------------------------------------- #
def _rec_travel(payload: dict) -> tuple[dict, dict]:
    try:
        baseline = TravelMode(str(payload.get("mode", "car_petrol")).lower())
    except ValueError:
        baseline = TravelMode.CAR_PETROL
    trip = Trip(
        name=payload.get("title", "Business trip"),
        distance_km=max(0.0, float(payload.get("distance_km", 0) or 0)),
        mode=baseline,
        round_trip=bool(payload.get("round_trip", True)),
    )
    d = optimize_trip(trip)
    virtual = d.chosen_mode == TravelMode.VIRTUAL
    if virtual:
        headline = "Hold this as a virtual meeting (no travel needed)."
    else:
        headline = f"Travel by {_LABEL.get(d.chosen_mode.value)} instead of {_LABEL.get(d.baseline_mode.value)}."
    rec = {
        "headline": headline,
        "kg_saved": round(d.kg_co2_saved, 1),
        "pct_saved": round(d.pct_saved, 0),
        "money_saved": round(d.money_saved, 0),
        "risk": d.risk.value,
        "rationale": d.classification_note or d.rationale,
        "citations": list(d.citations or []),
        "override_action": "travel in person",
    }
    inputs = {
        "distance_km": trip.distance_km,
        "round_trip": trip.round_trip,
        "submitted_mode": baseline.value,
        "essential": bool(trip.essential),
        "relationship_critical": bool(trip.relationship_critical),
    }
    return rec, inputs


def _rec_compute(payload: dict) -> tuple[dict, dict]:
    now = datetime.now(timezone.utc)
    power = max(0.0, float(payload.get("power_kw", 0) or 0))
    duration = max(0.1, float(payload.get("duration_hours", 1) or 1))
    due_in = max(duration, float(payload.get("due_in_hours", 12) or 12))
    job = Job(
        name=payload.get("title", "Compute workload"),
        power_kw=power,
        duration_hours=duration,
        deadline=now + timedelta(hours=due_in),
        earliest_start=now,
        flexible=True,
    )
    d = optimize_job(job, get_forecast(now=now))
    if d.chosen_start != d.baseline_start:
        headline = (
            f"Shift the run to {d.chosen_start:%a %H:%M} UTC — a greener grid window "
            f"({d.baseline_intensity:.0f} → {d.chosen_intensity:.0f} gCO₂/kWh)."
        )
    else:
        headline = "Run as planned — already in the cleanest available window."
    rec = {
        "headline": headline,
        "kg_saved": round(d.kg_co2_saved, 1),
        "pct_saved": round(d.pct_saved, 0),
        "money_saved": round(d.money_saved, 0),
        "risk": d.risk.value,
        "rationale": d.rationale,
        "citations": list(d.citations or []),
        "override_action": "run the workload now",
    }
    inputs = {
        "power_kw": power,
        "duration_hours": duration,
        "due_in_hours": due_in,
    }
    return rec, inputs


def _rec_fleet(payload: dict) -> tuple[dict, dict]:
    try:
        fuel = FuelType(str(payload.get("fuel", "diesel")).lower())
    except ValueError:
        fuel = FuelType.DIESEL
    vehicle = Vehicle(
        name=payload.get("title", "Fleet vehicle"),
        daily_km=max(0.0, float(payload.get("daily_km", 0) or 0)),
        fuel=fuel,
        ev_range_km=max(1.0, float(payload.get("ev_range_km", 250) or 250)),
        depot_charging=bool(payload.get("depot_charging", True)),
    )
    d = optimize_vehicle(vehicle)
    rec = {
        "headline": d.action + ".",
        "kg_saved": round(d.kg_co2_saved, 1),
        "pct_saved": round(d.pct_saved, 0),
        "money_saved": round(d.money_saved, 0),
        "risk": d.risk.value,
        "rationale": d.rationale,
        "citations": list(d.citations or []),
        "override_action": "keep the current vehicle/fuel",
    }
    inputs = {
        "daily_km": vehicle.daily_km,
        "fuel": fuel.value,
        "ev_range_km": vehicle.ev_range_km,
        "depot_charging": vehicle.depot_charging,
    }
    return rec, inputs


def _rec_procurement(payload: dict) -> tuple[dict, dict]:
    cost = max(0.0, float(payload.get("cost", 0) or 0))
    name = payload.get("title", "Purchased item")
    if payload.get("kg_co2e") not in (None, ""):
        kg = float(payload["kg_co2e"])
        kg_source = "supplied figure"
    else:
        kg, kg_source = estimate_embodied_kg(name, cost)
    line = PurchaseLine(name=name, kg_co2e=kg, cost=cost)  # no vetted alt => agent reasons
    d = optimize_purchase(line)
    rec = {
        "headline": d.action + ".",
        "kg_saved": round(d.kg_co2_saved, 1),
        "pct_saved": round(d.pct_saved, 0),
        "money_saved": round(d.money_saved, 0),
        "risk": d.risk.value,
        "rationale": d.rationale,
        "citations": list(d.citations or []),
        "override_action": "keep the current supplier/item",
    }
    inputs = {
        "cost": cost,
        "kg_co2e": round(kg, 1),
        "kg_source": kg_source,
    }
    return rec, inputs


_BUILDERS = {
    "compute": _rec_compute,
    "travel": _rec_travel,
    "fleet": _rec_fleet,
    "procurement": _rec_procurement,
}

_DOMAIN_LABEL = {
    "compute": "Compute workload",
    "travel": "Business travel",
    "fleet": "Fleet",
    "procurement": "Procurement",
}


def submit_request(domain: str, requester: str, email: str, title: str, **payload) -> dict:
    """Run the relevant agent reasoning on a request and record it.

    ``domain`` is one of :data:`DOMAINS`. ``payload`` carries the domain-specific
    fields (e.g. ``distance_km`` for travel, ``power_kw`` for compute). Writes the
    response email to disk and returns the stored record (status ``pending``).
    """
    domain = domain if domain in _BUILDERS else "travel"
    payload["title"] = title.strip() or _DOMAIN_LABEL[domain]
    rec, inputs = _BUILDERS[domain](payload)

    record = {
        "id": uuid.uuid4().hex[:8],
        "domain": domain,
        "manager": requester.strip() or "Unknown requester",
        "email": email.strip(),
        "purpose": payload["title"],
        "status": "pending",
        "reason": "",
        "created": datetime.now(timezone.utc).isoformat(),
        "decided": None,
        "inputs": inputs,
        "rec": rec,
    }

    records = _load()
    records.append(record)
    _save(records)

    _write_eml(record)
    return record


def decide(rid: str, decision: str, reason: str = "") -> dict | None:
    """Record the requester's Accept / Override choice for a request."""
    records = _load()
    for r in records:
        if r["id"] == rid:
            r["status"] = "overridden" if decision == "override" else "accepted"
            r["reason"] = reason.strip()
            r["decided"] = datetime.now(timezone.utc).isoformat()
            _save(records)
            return r
    return None


# --------------------------------------------------------------------------- #
# Dashboard feed
# --------------------------------------------------------------------------- #
@dataclass
class DashboardFeed:
    jobs: list[Job] = field(default_factory=list)
    trips: list[Trip] = field(default_factory=list)
    vehicles: list[Vehicle] = field(default_factory=list)
    purchases: list[PurchaseLine] = field(default_factory=list)
    override_reasons: dict[str, str] = field(default_factory=dict)
    managers: dict[str, str] = field(default_factory=dict)


def dashboard_feed() -> DashboardFeed:
    """Decided requests across every domain, ready to append to the team dashboard.

    Overridden items are forced to keep their original carbon-heavier choice (compute
    runs now, trips stay physical, vehicles keep their fuel, purchases keep supplier)
    and exposed via ``override_reasons`` so the dashboard can flag them.
    """
    feed = DashboardFeed()
    now = datetime.now(timezone.utc)
    for r in _load():
        if r["status"] not in ("accepted", "overridden"):
            continue
        overridden = r["status"] == "overridden"
        domain = r.get("domain", "travel")
        inp = r.get("inputs", {})
        name = r["purpose"]
        feed.managers[name] = r["manager"]
        if overridden:
            feed.override_reasons[name] = r["reason"] or "Requester elected to keep the original choice."

        if domain == "travel":
            try:
                mode = TravelMode(inp.get("submitted_mode", "car_petrol"))
            except ValueError:
                mode = TravelMode.CAR_PETROL
            feed.trips.append(Trip(
                name=name,
                distance_km=float(inp.get("distance_km", 0.0)),
                mode=mode,
                round_trip=bool(inp.get("round_trip", True)),
                essential=overridden or bool(inp.get("essential")),
                relationship_critical=bool(inp.get("relationship_critical")),
            ))
        elif domain == "compute":
            due_in = float(inp.get("due_in_hours", 12.0))
            feed.jobs.append(Job(
                name=name,
                power_kw=float(inp.get("power_kw", 0.0)),
                duration_hours=float(inp.get("duration_hours", 1.0)),
                deadline=now + timedelta(hours=due_in),
                earliest_start=now,
                # Override = run now, no shifting.
                flexible=not overridden,
            ))
        elif domain == "fleet":
            try:
                fuel = FuelType(inp.get("fuel", "diesel"))
            except ValueError:
                fuel = FuelType.DIESEL
            feed.vehicles.append(Vehicle(
                name=name,
                daily_km=float(inp.get("daily_km", 0.0)),
                fuel=fuel,
                ev_range_km=float(inp.get("ev_range_km", 250.0)),
                depot_charging=bool(inp.get("depot_charging", True)),
                # Override = keep current fuel (block EV swap).
                swappable_to_ev=not overridden,
            ))
        elif domain == "procurement":
            feed.purchases.append(PurchaseLine(
                name=name,
                kg_co2e=float(inp.get("kg_co2e", 0.0)),
                cost=float(inp.get("cost", 0.0)),
                # Override = keep current supplier (no switch).
                locked=overridden,
            ))
    return feed


# --------------------------------------------------------------------------- #
# Email rendering
# --------------------------------------------------------------------------- #
_LABEL = {
    "car_petrol": "petrol car",
    "car_ev": "electric car",
    "rail": "rail",
    "virtual": "a virtual meeting",
}

_SUBJECT_NOUN = {
    "compute": "Compute scheduling recommendation",
    "travel": "Travel recommendation",
    "fleet": "Fleet recommendation",
    "procurement": "Procurement recommendation",
}


def email_subject(record: dict) -> str:
    noun = _SUBJECT_NOUN.get(record.get("domain", "travel"), "Recommendation")
    return f"{noun} · {record['purpose']}"


def email_text(record: dict) -> str:
    """Plain-text body of the response email (also used for the on-screen preview)."""
    rec = record["rec"]
    domain_label = _DOMAIN_LABEL.get(record.get("domain", "travel"), "request")
    accept_url = f"{SERVER_BASE}/request/decision?id={record['id']}&decision=accept"
    override_url = f"{SERVER_BASE}/request/decision?id={record['id']}&decision=override"

    lines = [
        f"Hi {record['manager'].split()[0] if record['manager'] else 'there'},",
        "",
        f"Thanks for submitting your {domain_label.lower()} request: \"{record['purpose']}\".",
        "Our sustainability co-pilot reviewed it. Here is the recommendation:",
        "",
        f"  • {rec['headline']}",
        f"  • Why: {rec['rationale']}",
        f"  • Estimated saving: {rec['kg_saved']:.0f} kg CO2e ({rec['pct_saved']:.0f}%)"
        f" and {rec['money_saved']:.0f} in cost.",
        f"  • Risk rating: {rec['risk'].upper()}.",
    ]
    if rec.get("citations"):
        lines.append(f"  • Grounded in: {', '.join(rec['citations'])}.")
    lines += [
        "",
        "What would you like to do?",
        f"  ACCEPT this recommendation:  {accept_url}",
        f"  OVERRIDE ({rec.get('override_action', 'keep the original choice')}): {override_url}",
        "",
        "If you override, the carbon-reduction team will see your request flagged with",
        "your reason so they can plan around it. Your deadline is always honoured.",
        "",
        "— CarbonShift Sustainability Co-Pilot",
    ]
    return "\n".join(lines)


def _write_eml(record: dict) -> str:
    """Persist the response email as a .eml file (no SMTP needed for the demo)."""
    msg = EmailMessage()
    msg["From"] = FROM_ADDRESS
    msg["To"] = record["email"] or "requester@contoso.com"
    msg["Subject"] = email_subject(record)
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg.set_content(email_text(record))

    path = os.path.join(_emails_dir(), f"{record['id']}.eml")
    with open(path, "wb") as fh:
        fh.write(bytes(msg))
    return path
