# CarbonShift — Demo Script & Run Sheet

A 2–3 minute walkthrough for the Agents League Hackathon submission video.
Keep this open on a second monitor while recording.

---

## A. Before you record (one-time prep, ~5 min)

Start from a clean, known state:

```powershell
cd C:\Hack\carbonshift
python demo_inject.py clear          # wipe any injected data -> baseline
python demo_inject.py spike off      # make sure no grid spike is active
```

Start the dashboard and let it fully load **once** before recording (the first render
is slow — it runs the live LLM + grid pipeline):

```powershell
python run_web.py
```

Open **http://127.0.0.1:5000/?scenario=relaxed** and wait until the cards, the Agent
team transcript, and the plain-English summary are all visible. Leave it on screen.

> ⏱️ **Timing:** after each `demo_inject.py` command the dashboard re-plans within a few
> seconds, but the full re-render runs the live agents and can take up to ~1–2 minutes.
> Trim that dead time when editing, or narrate while it works.

**Layout:** browser (dashboard) on the left, terminal on the right, so the audience sees
you run a command and the dashboard update.

**Also pre-open** a second browser tab on the Azure portal at the Foundry AI Search index
(`carbonshift-search-8865` → Indexes → `carbon-knowledge`) and sign in beforehand, so
Scene 2.5 has no loading or login on camera.

---

## B. How to record (no extra software)

- **Start/stop:** **Win + Alt + R** (Windows Game Bar) — records the active window + audio.
- Or **Win + G** → Capture widget → record. Enable the microphone in Game Bar settings.
- **Edit/trim** with **Clipchamp** (built into Windows) — cut the slow re-plan gaps.
- Keep it **2–3 minutes**. Export **1080p MP4**.

---

## C. Run sheet (scene by scene)

### Scene 1 — Hook & problem (~20s) · on the dashboard
> "This is CarbonShift — an organizational sustainability co-pilot. Electricity is about
> a quarter of global emissions, and the grid's carbon intensity swings two-to-five times
> a day. Most flexible work runs at the dirtiest, most expensive times. CarbonShift is a
> team of eight AI agents on Microsoft Foundry that retimes and reroutes compute, travel,
> fleet, and procurement to cut both carbon and cost — without missing a single deadline."

**Do:** Point at the four domain cards, then the live **Grid** intensity pill up top.

### Scene 2 — The agent team (~25s) · scroll to Agent team panel
> "An Orchestrator coordinates the agents over a shared blackboard. ForecastAgent reads
> the live UK grid; OptimizerAgent schedules compute into the cleanest window; TravelAgent,
> FleetAgent and ProcurementAgent each handle their domain; and an independent RiskAgent
> re-checks every decision and can send the plan back for revision. Everything's grounded
> in Foundry IQ — the required Microsoft IQ layer — so each figure is cited."

**Do:** Scroll through the **Agent team** transcript. Point out the two lines that *prove*
the IQ layer is live: TravelAgent's *"Classified in-person need … via Foundry IQ"* and
ProcurementAgent's *"…selected greener options … via Foundry IQ"*, plus the **✦ AI**
reasoning text on travel/procurement rows.

### Scene 2.5 — Proof it runs on Microsoft Foundry (~25s) · switch to browser tab

> "And this isn't a mock. The reasoning agents call a **gpt-4o** deployment in our
> Microsoft Foundry project, and every fact is grounded in **Foundry IQ** — the required
> Microsoft IQ layer — backed by an Azure AI Search index called `carbon-knowledge`."

**Do (in this order, in the Azure tab):**
1. Show the **Azure AI Search** resource `carbonshift-search-8865` → **Indexes** →
   open **`carbon-knowledge`** — point at **Documents: 10** (the index is populated).
2. In the **Search explorer**, type `*` and click **Search** so the real knowledge
   documents (emission factors, grid intensity, scheduling policy) list out.
3. *(Optional, ~3s)* Flash `agent.yaml` and `knowledge/` in VS Code so they see the
   gpt-4o model + the cited source docs wired in.

> ⚠️ **On camera:** scroll past any panel that shows your full subscription GUID or
> account email — keep identifiers off a public video.
> ℹ️ The Foundry portal's **Knowledge → Indexes** page may read *"No indexes available"* —
> that's only the project-level registration view; the app reads the Search index
> directly, so show the **`carbonshift-search-8865`** tab (above), not that page.

### Scene 3 — Live data injection, one agent at a time (~80s)

> "Now let's give the agents data they've never seen — live, no restart. One domain at a time."

**Run:**
```powershell
python demo_inject.py compute
```
> "A new GPU job. The OptimizerAgent slots it into the greenest grid window before its
> deadline — and the RiskAgent guarantees the deadline is still met."

**Run:**
```powershell
python demo_inject.py travel
```
> "A new trip with a deliberately vague name and no flags. The LLM travel classifier,
> grounded in Foundry IQ, decides the in-person need itself — a factory inspection reads
> as essential, so it stays physical but on the cleanest mode."
> *(Run `travel` again to add the investor roadshow — that one classifies as
> relationship-critical and triggers a RiskAgent negotiation round — watch the
> ⇄ badge in the Agent team header.)*

**Run:**
```powershell
python demo_inject.py fleet
```
> "A new delivery van. The FleetAgent routes it against EV range and live charger-map
> data, and recommends electrifying it."

**Run:**
```powershell
python demo_inject.py procurement
```
> "And an unfamiliar purchase the agent has never seen. The ProcurementAgent reasons
> about it autonomously via Foundry IQ and proposes a greener alternative — flagged with
> a sparkle as an AI decision."

**Do:** After each command, point to the new row appearing in the matching card
(✦ AI markers on travel & procurement).

### Scene 4 — Grid stress test (~20s)
**Run:**
```powershell
python demo_inject.py spike
```
> "Now simulate a grid-stress event — carbon intensity jumps. The agents re-plan around
> it automatically, and the grid pill flags the simulated spike."

**Run (clear it):**
```powershell
python demo_inject.py spike off
```

### Scene 5 — Human-in-the-loop request portal (~25s)
**Do:** Click **➕ Request portal** (top right) → open a domain form → submit one request →
show the **Accept** / **Override** buttons on the recommendation screen.
> "It's not just automatic. Managers submit requests through the portal and get a
> Foundry-IQ-grounded recommendation they can accept — which flows onto the board with
> its AI marker — or override with a reason, flagged in red. Human decisions are always
> authoritative."

### Scene 6 — Time window & honest totals (~20s)
**Do:** Open the **🕑 time-window selector** (top bar) — show **Last 24 hours / live** as
the default — then the headline totals.
> "The whole view is anchored to a chosen moment — defaulting to the last 24 hours, live —
> and the CostAgent rolls everything into one honest headline: estimated annual tonnes of
> CO₂ avoided and pounds saved, with assumptions shown. That's CarbonShift — transparent,
> multi-agent, deadline-safe carbon and cost reduction. Thanks for watching."

---

## D. Command reference (all from `C:\Hack\carbonshift`)

| Purpose | Command |
| --- | --- |
| Reset to baseline (before recording) | `python demo_inject.py clear` |
| Push compute job (OptimizerAgent) | `python demo_inject.py compute` |
| Push business trip (TravelAgent) | `python demo_inject.py travel` |
| Push vehicle (FleetAgent) | `python demo_inject.py fleet` |
| Push purchase (ProcurementAgent) | `python demo_inject.py procurement` |
| Simulate grid spike | `python demo_inject.py spike` |
| Clear spike | `python demo_inject.py spike off` |
| Push a mixed wave (legacy) | `python demo_inject.py wave 2` |
| Check what's injected | `python demo_inject.py status` |
| Start dashboard | `python run_web.py` |

**Reset between practice runs:** `python demo_inject.py clear; python demo_inject.py spike off`

> Each per-domain command cycles through 3 curated items, so you can run the same one
> several times to add successive items during the demo.
