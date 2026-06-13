# CarbonShift — Session Notes (resume guide)

_Last updated: 2026-06-11_

## How to restart everything
```powershell
# Start the dashboard
python C:\Hack\carbonshift\run_web.py
# Then open:
#   http://127.0.0.1:5000/?scenario=relaxed
```
The Flask server runs with `debug=False` (no auto-reload) — **restart it after any
change to `carbonshift/web.py`**. To stop a stale server on port 5000:
```powershell
Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
```

## Demo commands (backend-driven; no fabricate-data controls in the UI)
Run from `C:\Hack\carbonshift`:
```powershell
python demo_inject.py            # apply next wave of injected items
python demo_inject.py wave 2     # apply a specific wave
python demo_inject.py status     # show current injected state + spike
python demo_inject.py clear      # reset all injection back to baseline
python demo_inject.py spike      # simulate a grid spike (+180 gCO2/kWh)
python demo_inject.py spike 220  # custom spike value
python demo_inject.py spike off  # clear the spike (revert to live grid)
```
The dashboard polls `/api/version` every 3s and live-re-renders when the injection
file changes — no page reload needed.

## Manager travel-request portal (separate from the team dashboard)
- The team dashboard (`/`) is operated by the carbon-reduction team only.
- Managers submit trips at **`/request`** (linked from the dashboard topbar). They get
  an emailed recommendation (rendered on screen + saved as `manager_emails/<id>.eml`)
  with **Accept** / **Override** actions.
- **Accept** → trip flows onto the team dashboard with its ✦ AI marker + saving.
- **Override** → manager gives a reason; the trip is forced physical and flagged on the
  team dashboard with a red **⚑ Manager override** badge + reason.
- Code: `carbonshift/requests_store.py` (submit/decide/dashboard_feed/email + .eml).
  Persists to `manager_requests.json`; `store_version()` folds into `_feed_version()`
  so the dashboard auto-refreshes on a manager decision. Routes in `web.py`:
  `/request` (GET form, POST submit) and `/request/decision` (accept/override).
  Reset demo: `Remove-Item manager_requests.json, manager_emails -Recurse -Force`.

## What this app is
Multi-agent organizational sustainability co-pilot. An `Orchestrator` coordinates an
8-agent team over a shared `Blackboard`, running a RiskAgent-led negotiation loop
(`MAX_NEGOTIATION_ROUNDS = 3`) before finalising. Backed by Microsoft Foundry
(gpt-4o) + Foundry IQ (Azure AI Search), live UK grid data, and real OpenStreetMap
charger data.

### Agent pipeline (in `carbonshift/agents/`)
Orchestrator ➜ ForecastAgent → OptimizerAgent → TravelAgent →
FleetAgent → ProcurementAgent → **RiskAgent** (reviewer) → CostAgent → BriefingAgent (LLM)

_The Facilities domain was fully removed (the `facilities.py` / `facilities_agent.py`
modules, the `Facility` model, `demo_facilities()`, and all blackboard/cost/risk/briefing
references are gone). The demo now focuses on four domains: compute, travel, fleet, and
procurement._

- `orchestrator.py` — coordinator; splits team into proposers/reviewer/finalisers,
  runs the review/revise loop, dispatches `revise()` requests.
- `risk_agent.py` — reviewer; sends `revision.requested` back when a job finishes too
  close to its deadline or an essential trip is downgraded.
- `briefing_agent.py` — only LLM agent; writes the grounded, cited operator briefing
  (falls back to a deterministic local template if Foundry isn't configured).

## Recently completed (this session)
- **Compute-job injection** — injected jobs flow through the optimizer live.
- **Production theme** — emerald/teal graphite palette (replaced default-AI navy).
- **Backend-driven grid spike** — moved off the UI; `demo_inject.py spike`; removed the
  button markup/CSS/JS. `SIMULATED` tag still shows on the grid pill when active.
- **Orchestrator surfaced in UI** — Agent team panel header reads
  "Agent team · 9 agents · orchestrated"; pipeline leads with a highlighted
  `⚙ Orchestrator` node + tooltip; `⇄ N negotiation round` badge.
- **LLM trip classifier** — `carbonshift/travel_classifier.py` (gpt-4o grounded in
  Foundry IQ + keyword heuristic fallback) reasons about each trip's in-person need
  (essential / relationship_critical) from the trip name, instead of relying only on
  preset flags. Human-set flags are an authoritative FLOOR (AI can add a requirement,
  never override a human one). Surfaced as ✦ AI + reasoning on every Business-travel row;
  TravelAgent transcript says "Classified in-person need … via Foundry IQ". Wave 3 of
  `demo_inject.py` now has 3 descriptive trips (factory inspection=essential, investor
  roadshow=relationship-critical→triggers a negotiation round, monthly review=flexible).

## Current state
- Server running on :5000. Injection **cleared** (baseline). Grid spike **off**
  (live grid ~167 gCO₂/kWh).

## Gotchas
- `web.py` changes need a server restart (no auto-reload).
- `/api/state` runs the full pipeline (slow, ~1–3 min with LLM + live calls);
  `/api/version` is cheap and used for polling.
- The embedded automation browser can show a stale CACHED page — reload to verify.
- JSON can't store datetimes — injected compute-job deadlines use relative
  `due_in_hours`.
- Run `demo_inject.py` from `C:\Hack\carbonshift` (or use the absolute path).

## Deferred / possible next steps
- Per-row live/est badge in the UI.
- README update (negotiation loop, agentic procurement, route-aware fleet, live
  injection, compute injection, backend spike, new theme).
- Demo narration script.
- GitHub push (note: `gh` CLI not installed).
