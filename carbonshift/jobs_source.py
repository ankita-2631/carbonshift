"""Compute-workload data source.

In production, CarbonShift pulls flexible compute jobs from the organization's job
scheduler / batch queue (e.g. a Kubernetes CronJob inventory, Airflow, Slurm, an
internal batch API). Set the ``JOBS_API`` environment variable to a JSON endpoint
that returns a list of jobs; each is mapped to a :class:`Job`.

When no endpoint is configured (or it is unreachable), CarbonShift falls back to the
bundled demo jobs for the selected scenario so the demo always runs.

Expected job JSON (per item)::

    {
        "name": "Nightly model fine-tune (GPU cluster)",
        "power_kw": 120.0,
        "duration_hours": 4.0,
        "deadline_hours": 14,        # hours from now
        "earliest_start_hours": 0,   # hours from now (optional)
        "region": "national",        # optional
        "flexible": true             # optional, default true
    }
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

from .models import Job
from .sample_data import SCENARIOS, demo_jobs

JOBS_API = os.environ.get("JOBS_API", "")
JOBS_API_TOKEN = os.environ.get("JOBS_API_TOKEN", "")


class JobSource:
    """Jobs plus a label describing where they came from."""

    def __init__(self, jobs: list[Job], source: str):
        self.jobs = jobs
        self.source = source


def _job_from_payload(j: dict, now: datetime) -> Job:
    earliest = j.get("earliest_start_hours")
    return Job(
        name=str(j["name"]),
        power_kw=float(j["power_kw"]),
        duration_hours=float(j["duration_hours"]),
        deadline=now + timedelta(hours=float(j["deadline_hours"])),
        earliest_start=now + timedelta(hours=float(earliest)) if earliest is not None else now,
        region=str(j.get("region", "national")),
        flexible=bool(j.get("flexible", True)),
    )


def get_jobs(scenario: str = "relaxed", now: datetime | None = None) -> JobSource:
    """Pull flexible jobs from the org scheduler, or fall back to demo data."""
    now = now or datetime.now(timezone.utc)
    if not JOBS_API:
        factory = SCENARIOS.get(scenario, demo_jobs)
        return JobSource(factory(now=now), source=f"demo-jobs ({scenario}, no scheduler configured)")
    try:
        headers = {"Authorization": f"Bearer {JOBS_API_TOKEN}"} if JOBS_API_TOKEN else {}
        resp = requests.get(JOBS_API, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("jobs", data) if isinstance(data, dict) else data
        jobs = [_job_from_payload(j, now) for j in items]
        if not jobs:
            factory = SCENARIOS.get(scenario, demo_jobs)
            return JobSource(factory(now=now), source="demo-jobs (scheduler returned none)")
        return JobSource(jobs, source=f"scheduler: {JOBS_API}")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        factory = SCENARIOS.get(scenario, demo_jobs)
        return JobSource(factory(now=now), source="demo-jobs (scheduler unavailable)")
