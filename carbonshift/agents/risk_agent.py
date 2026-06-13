"""RiskAgent — independently verifies the plans against hard safety constraints.

This is the guardrail. It does NOT trust the optimizers blindly: it re-checks every
schedule decision against the job's deadline and earliest-start, confirms inflexible
jobs were not moved, and verifies essential trips were not sent virtual. It tallies the
traffic-light ratings across both domains. If any constraint is violated it raises a
safety flag that downstream agents must surface.

It can also actively negotiate. If a shifted compute job would finish with too little
headroom before its deadline, the RiskAgent sends the plan *back* to the OptimizerAgent
asking it to re-plan with a safety buffer. If the TravelAgent downgrades a
relationship-critical trip to a virtual call (against travel policy), it sends that back
too, asking for the cleanest *physical* mode instead. This makes the team genuinely
agentic — proposals are critiqued and revised, not rubber-stamped.
"""
from __future__ import annotations

from datetime import timedelta

from ..models import RiskLevel, TravelMode
from .base import Agent, AgentMessage, Blackboard, RevisionRequest

# A shifted job should finish at least this far before its deadline.
SAFETY_BUFFER_HOURS = 0.75  # 45 minutes


class RiskAgent(Agent):
    """Validates the proposed plans (compute + travel) and produces a safety verdict."""

    name = "RiskAgent"

    def process(self, bb: Blackboard) -> list[AgentMessage]:
        if bb.plan is None:
            raise RuntimeError("RiskAgent ran before a plan was proposed.")

        violations: list[str] = []
        counts = {RiskLevel.GREEN: 0, RiskLevel.AMBER: 0, RiskLevel.RED: 0}
        tight: list[str] = []          # shifted jobs that finish without enough headroom
        keep_physical: list[str] = []  # relationship-critical trips downgraded to virtual

        for d in bb.plan.decisions:
            counts[d.risk] += 1
            job = d.job
            finish = d.chosen_start + timedelta(hours=job.duration_hours)

            # Hard constraint 1: never finish after the deadline.
            if finish > job.deadline + timedelta(seconds=1):
                violations.append(
                    f"{job.name}: finishes {finish:%H:%M} after deadline {job.deadline:%H:%M}."
                )
            # Hard constraint 2: never start before earliest_start.
            earliest = job.earliest_start or bb.now
            if d.chosen_start < earliest - timedelta(seconds=1):
                violations.append(
                    f"{job.name}: starts before earliest permitted time."
                )
            # Hard constraint 3: inflexible jobs must not be shifted.
            if not job.flexible and d.chosen_start != d.baseline_start:
                violations.append(f"{job.name}: inflexible job was shifted.")

            # Negotiable concern: a shifted job that finishes too close to the
            # deadline. Only worth raising if a buffer can actually fit and we
            # have not already applied one (avoids an infinite back-and-forth).
            headroom = job.deadline - finish
            buffer_fits = (
                earliest
                + timedelta(hours=job.duration_hours + SAFETY_BUFFER_HOURS)
                <= job.deadline
            )
            if (
                job.flexible
                and d.chosen_start != d.baseline_start
                and headroom < timedelta(hours=SAFETY_BUFFER_HOURS)
                and buffer_fits
                and bb.applied_safety_buffer_hours <= 0.0
            ):
                tight.append(job.name)

        # Validate travel decisions too.
        if bb.travel_plan is not None:
            for t in bb.travel_plan.decisions:
                counts[t.risk] += 1
                # Hard constraint 4: essential trips must not be made virtual.
                if t.trip.essential and t.chosen_mode == TravelMode.VIRTUAL:
                    violations.append(
                        f"{t.trip.name}: essential trip was recommended as virtual."
                    )
                # Negotiable concern: a relationship-critical trip downgraded to
                # virtual against travel policy. Ask for the cleanest physical mode.
                if (
                    t.trip.relationship_critical
                    and t.chosen_mode == TravelMode.VIRTUAL
                    and t.trip.name not in bb.keep_physical_trips
                ):
                    keep_physical.append(t.trip.name)

        # Validate the measure-based domains (fleet, procurement).
        for measure_plan in (bb.fleet_plan, bb.procurement_plan):
            if measure_plan is None:
                continue
            for m in measure_plan.decisions:
                counts[m.risk] += 1
                # Hard constraint 5: a recommendation must never increase emissions.
                if m.kg_co2_chosen > m.kg_co2_baseline + 1e-6:
                    violations.append(
                        f"{m.name}: recommended action increases emissions."
                    )

        bb.risk_counts = {k.value: v for k, v in counts.items()}
        bb.safety_violations = violations

        # If we have negotiable concerns (and no hard violations), send work back to
        # the responsible proposer agents to re-plan. Multiple requests can be raised
        # in one round; the orchestrator dispatches each to its target.
        bb.revision_requests = []
        if (tight or keep_physical) and not violations:
            asks: list[str] = []
            if tight:
                names = ", ".join(tight)
                bb.revision_requests.append(
                    RevisionRequest(
                        target="OptimizerAgent",
                        reason=f"{len(tight)} job(s) finish within "
                        f"{SAFETY_BUFFER_HOURS * 60:.0f} min of deadline ({names})",
                        constraints={"safety_buffer_hours": SAFETY_BUFFER_HOURS},
                    )
                )
                asks.append(
                    f"OptimizerAgent to add a {SAFETY_BUFFER_HOURS * 60:.0f}-min "
                    f"buffer for {len(tight)} job(s)"
                )
            if keep_physical:
                names = ", ".join(keep_physical)
                bb.revision_requests.append(
                    RevisionRequest(
                        target="TravelAgent",
                        reason=f"{len(keep_physical)} relationship-critical trip(s) "
                        f"downgraded to virtual ({names})",
                        constraints={"keep_physical": keep_physical},
                    )
                )
                asks.append(
                    f"TravelAgent to keep {len(keep_physical)} trip(s) in person"
                )

            verdict = "REVISION REQUESTED: " + "; ".join(asks) + "."
            bb.risk_ok = False
            bb.risk_verdict = verdict
            emitted: list[AgentMessage] = []
            for req in bb.revision_requests:
                m = AgentMessage(
                    sender=self.name,
                    recipient=req.target,
                    intent="revision.requested",
                    summary=f"Re-plan: {req.reason}.",
                    payload=req.constraints,
                )
                bb.post(m)
                emitted.append(m)
            return emitted

        bb.risk_ok = not violations
        if violations:
            verdict = f"BLOCKED: {len(violations)} safety violation(s) detected."
        else:
            notes = []
            if bb.applied_safety_buffer_hours > 0.0:
                notes.append(
                    f"{bb.applied_safety_buffer_hours * 60:.0f}-min compute buffer"
                )
            if bb.keep_physical_trips:
                notes.append(
                    f"{len(bb.keep_physical_trips)} trip(s) kept in person"
                )
            suffix = ""
            if notes:
                suffix = (
                    f" after {bb.negotiation_rounds} negotiation round"
                    f"{'s' if bb.negotiation_rounds != 1 else ''} "
                    f"({', '.join(notes)})"
                )
            verdict = (
                f"APPROVED: all deadlines honoured{suffix}. "
                f"{counts[RiskLevel.GREEN]} green, {counts[RiskLevel.AMBER]} amber, "
                f"{counts[RiskLevel.RED]} red."
            )
        bb.risk_verdict = verdict

        msg = AgentMessage(
            sender=self.name,
            recipient="CostAgent",
            intent="safety.verdict",
            summary=verdict,
            payload={
                "ok": bb.risk_ok,
                "counts": bb.risk_counts,
                "violations": violations,
            },
        )
        bb.post(msg)
        return [msg]
