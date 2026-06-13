"""Carbon-aware scheduling optimizer.

Given a job and a carbon forecast, find the start time that minimises CO2 while
honouring the job's earliest-start and deadline constraints. This is the
deterministic reasoning core that the agent explains in natural language.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .carbon_data import CarbonForecast
from .models import Job, RiskLevel, ScheduleDecision, SchedulePlan
from .pricing import energy_cost

# Below this % saving we rate AMBER; at/above we rate GREEN.
GREEN_THRESHOLD_PCT = 15.0


def _kg_co2(power_kw: float, duration_hours: float, gco2_per_kwh: float) -> float:
    """Energy (kWh) * intensity (gCO2/kWh) -> kg CO2."""
    kwh = power_kw * duration_hours
    grams = kwh * gco2_per_kwh
    return grams / 1000.0


def optimize_job(
    job: Job,
    forecast: CarbonForecast,
    now: datetime | None = None,
    slot_minutes: int = 30,
    safety_buffer_hours: float = 0.0,
) -> ScheduleDecision:
    """Find the lowest-carbon start time for a single job within its constraints.

    ``safety_buffer_hours`` shrinks the usable deadline so the job finishes with
    headroom to spare. The RiskAgent uses this to negotiate a safer schedule.
    """
    now = now or datetime.now(timezone.utc)
    earliest = job.earliest_start or now
    baseline_start = earliest
    baseline_intensity = forecast.average_intensity(baseline_start, job.duration_hours)
    baseline_kg = _kg_co2(job.power_kw, job.duration_hours, baseline_intensity)
    baseline_cost = energy_cost(job.power_kw, job.duration_hours, baseline_intensity)

    # Inflexible jobs run immediately, no shifting.
    if not job.flexible:
        return ScheduleDecision(
            job=job,
            chosen_start=baseline_start,
            baseline_start=baseline_start,
            chosen_intensity=baseline_intensity,
            baseline_intensity=baseline_intensity,
            kg_co2_chosen=baseline_kg,
            kg_co2_baseline=baseline_kg,
            risk=RiskLevel.RED,
            rationale="Job is marked inflexible and must run now; no shifting possible.",
            cost_chosen=baseline_cost,
            cost_baseline=baseline_cost,
        )

    latest_start = job.deadline - timedelta(hours=job.duration_hours + safety_buffer_hours)
    if latest_start < earliest:
        # Deadline cannot accommodate the duration (plus buffer) from the earliest start.
        return ScheduleDecision(
            job=job,
            chosen_start=baseline_start,
            baseline_start=baseline_start,
            chosen_intensity=baseline_intensity,
            baseline_intensity=baseline_intensity,
            kg_co2_chosen=baseline_kg,
            kg_co2_baseline=baseline_kg,
            risk=RiskLevel.RED,
            rationale=(
                "Deadline is too tight to shift: the job must start now to finish in time."
            ),
            cost_chosen=baseline_cost,
            cost_baseline=baseline_cost,
        )

    # Scan candidate start times between earliest and latest_start.
    best_start = baseline_start
    best_intensity = baseline_intensity
    step = timedelta(minutes=slot_minutes)
    candidate = earliest
    while candidate <= latest_start:
        intensity = forecast.average_intensity(candidate, job.duration_hours)
        if intensity < best_intensity:
            best_intensity = intensity
            best_start = candidate
        candidate += step

    chosen_kg = _kg_co2(job.power_kw, job.duration_hours, best_intensity)
    chosen_cost = energy_cost(job.power_kw, job.duration_hours, best_intensity)
    saved_pct = 0.0 if baseline_kg <= 0 else 100.0 * (baseline_kg - chosen_kg) / baseline_kg

    if best_start == baseline_start or saved_pct < 1.0:
        risk = RiskLevel.AMBER
        rationale = "Running now is already near-optimal; little to gain from shifting."
    elif saved_pct >= GREEN_THRESHOLD_PCT:
        risk = RiskLevel.GREEN
        rationale = (
            f"Shifting to {best_start:%a %H:%M} UTC cuts intensity from "
            f"{baseline_intensity:.0f} to {best_intensity:.0f} gCO2/kWh while meeting the "
            f"{job.deadline:%a %H:%M} deadline."
        )
    else:
        risk = RiskLevel.AMBER
        rationale = (
            f"Modest saving available by shifting to {best_start:%a %H:%M} UTC; "
            f"deadline limits how clean a window we can reach."
        )

    return ScheduleDecision(
        job=job,
        chosen_start=best_start,
        baseline_start=baseline_start,
        chosen_intensity=best_intensity,
        baseline_intensity=baseline_intensity,
        kg_co2_chosen=chosen_kg,
        kg_co2_baseline=baseline_kg,
        risk=risk,
        rationale=rationale,
        cost_chosen=chosen_cost,
        cost_baseline=baseline_cost,
    )


def optimize_plan(
    jobs: list[Job],
    forecast: CarbonForecast,
    now: datetime | None = None,
    safety_buffer_hours: float = 0.0,
) -> SchedulePlan:
    """Optimize a list of jobs independently and aggregate the savings."""
    now = now or datetime.now(timezone.utc)
    plan = SchedulePlan()
    for job in jobs:
        plan.decisions.append(
            optimize_job(job, forecast, now=now, safety_buffer_hours=safety_buffer_hours)
        )
    return plan
