"""CarbonShift command-line interface.

Usage:
    python -m carbonshift.cli --demo
    python -m carbonshift.cli --demo --no-agent
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .agents import Orchestrator
from .jobs_source import get_jobs
from .pricing import CURRENCY_SYMBOL
from .sample_data import demo_purchases, demo_vehicles
from .travel_booking import get_trips


def run_demo(use_agent: bool = True) -> int:
    now = datetime.now(timezone.utc)
    job_src = get_jobs(now=now)
    jobs = job_src.jobs
    trip_src = get_trips()
    trips = trip_src.trips

    orchestrator = Orchestrator()
    bb = orchestrator.run(
        jobs,
        trips=trips,
        now=now,
        trip_source=trip_src.source,
        job_source=job_src.source,
        vehicles=demo_vehicles(),
        purchases=demo_purchases(),
    )
    plan = bb.plan
    travel = bb.travel_plan

    print("=" * 72)
    print("CarbonShift — organizational sustainability co-pilot")
    print(f"Forecast source: {bb.forecast.source}")
    print(f"Jobs source:     {bb.job_source}")
    print(f"Travel source:   {bb.trip_source}")
    print("=" * 72)

    # Show the agent-to-agent conversation.
    print("Agent transcript:")
    for m in bb.transcript:
        print(f"  {m.sender} -> {m.recipient} [{m.intent}]")
        print(f"      {m.summary}")
    print("-" * 72)

    print("Compute workloads:")
    for d in plan.decisions:
        print(
            f"[{d.risk.value.upper():5}] {d.job.name}\n"
            f"        run {d.chosen_start:%a %H:%M} UTC "
            f"(baseline {d.baseline_start:%a %H:%M}) | "
            f"{d.baseline_intensity:.0f} -> {d.chosen_intensity:.0f} gCO2/kWh | "
            f"saved {d.kg_co2_saved:.1f} kg, {CURRENCY_SYMBOL}{d.money_saved:.0f}"
        )

    print("\nBusiness travel:")
    for t in travel.decisions:
        print(
            f"[{t.risk.value.upper():5}] {t.trip.name}\n"
            f"        {t.baseline_mode.value} -> {t.chosen_mode.value} | "
            f"saved {t.kg_co2_saved:.1f} kg, {CURRENCY_SYMBOL}{t.money_saved:.0f}"
        )

    for title, mplan in (
        ("Fleet (per year)", bb.fleet_plan),
        ("Procurement (per year)", bb.procurement_plan),
    ):
        if not mplan or not mplan.decisions:
            continue
        print(f"\n{title}:")
        for m in mplan.decisions:
            print(
                f"[{m.risk.value.upper():5}] {m.name}\n"
                f"        {m.action} | saved {m.kg_co2_saved:.1f} kg, "
                f"{CURRENCY_SYMBOL}{m.money_saved:.0f}"
            )

    print("-" * 72)
    print(
        f"ESTIMATED ANNUAL IMPACT: {bb.total_kg_saved / 1000.0:.1f} tonnes CO2 avoided · "
        f"{CURRENCY_SYMBOL}{bb.total_money_saved:,.0f} saved"
    )
    print("(compute annualised daily; travel monthly; fleet & procurement already annual)")
    print(f"RiskAgent: {bb.risk_verdict}")
    print("=" * 72)

    if use_agent:
        print("\nBriefingAgent (gpt-4o + Foundry IQ):\n")
        print(bb.briefing)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="carbonshift", description="Carbon-aware scheduler")
    parser.add_argument("--demo", action="store_true", help="Run the built-in demo workloads")
    parser.add_argument("--no-agent", action="store_true", help="Skip the Foundry briefing text")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo(use_agent=not args.no_agent)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
