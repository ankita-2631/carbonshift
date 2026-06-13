"""CarbonShift web dashboard (Flask).

Run:
    python -m carbonshift.web
Then open http://127.0.0.1:5000
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask, render_template_string, request

from .agents import (
    CostAgent,
    FleetAgent,
    ForecastAgent,
    OptimizerAgent,
    Orchestrator,
    ProcurementAgent,
    RiskAgent,
    TravelAgent,
)
from .pricing import CURRENCY_SYMBOL
from .jobs_source import get_jobs
from .demo_feed import data_version, injected_spike, load_injected
from .sample_data import SCENARIOS, demo_purchases, demo_vehicles
from .travel_booking import get_trips
from . import requests_store


# Selectable dashboard time windows: label + length used to anchor the pipeline
# evaluation moment ("as of" the end of the window). Default is the last 24 hours.
_WINDOWS = {
    "24h": ("Last 24 hours", timedelta(hours=24)),
    "7d": ("Last 7 days", timedelta(days=7)),
    "30d": ("Last 30 days", timedelta(days=30)),
}


def _parse_at(raw: str | None) -> datetime | None:
    """Parse a datetime-local value (``YYYY-MM-DDTHH:MM``) into an aware UTC datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _feed_version() -> str:
    """Combined fingerprint of the demo feed and the manager-request store.

    Lets the dashboard auto-refresh both when the demo feed changes and when a
    manager accepts or overrides a recommendation.
    """
    return f"{data_version()}|{requests_store.store_version()}"

app = Flask(__name__)

# The dashboard does not render the LLM briefing text, so it runs every agent
# except BriefingAgent for a fast, fully-offline page load.
_DASHBOARD = Orchestrator(
    agents=[
        ForecastAgent(),
        OptimizerAgent(),
        TravelAgent(),
        FleetAgent(),
        ProcurementAgent(),
        RiskAgent(),
        CostAgent(),
    ]
)

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CarbonShift · Sustainability Co-Pilot</title>
  <style>
    :root {
      color-scheme: dark;
      /* Surfaces — true black (OLED) to minimise display energy use */
      --bg:#000000; --panel:#0a0a0a; --panel2:#101211; --line:#1c241f;
      --line2:#2a3a30; --txt:#e8f3ec; --mut:#8fb0a1; --mut2:#5f7d6f;
      /* Traffic-light semantics */
      --green:#34d399; --amber:#fbbf24; --red:#f87171; --cash:#f5c451;
      /* Brand — emerald → teal (carbon / sustainability) */
      --brand:#10b981; --brand2:#2dd4bf;
      --accent-soft:rgba(45,212,191,.14);
      --shadow:0 14px 34px -16px rgba(0,0,0,.9);
    }
    * { box-sizing: border-box; }
    html, body { height:100%; }
    body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif;
           margin: 0; color: var(--txt);
           background:
             radial-gradient(1200px 600px at 85% -14%, rgba(16,185,129,.10), transparent 60%),
             radial-gradient(1000px 520px at -10% 114%, rgba(45,212,191,.06), transparent 55%),
             #000000;
           -webkit-font-smoothing: antialiased; height:100vh; overflow:hidden;
           display:flex; flex-direction:column; }
    a { color: inherit; }

    /* ---- top bar ---- */
    .topbar { display:flex; align-items:center; gap:18px; flex:0 0 auto;
              padding: 11px 20px; border-bottom: 1px solid var(--line);
              background: linear-gradient(180deg, rgba(14,16,15,.94), rgba(0,0,0,.86));
              backdrop-filter: blur(10px); }
    .brand { display:flex; align-items:center; gap:10px; font-weight:700; font-size:1.05rem; }
    .logo { width:28px; height:28px; border-radius:9px; display:grid; place-items:center;
            background: linear-gradient(135deg,var(--brand),var(--brand2));
            font-size:.95rem; box-shadow:0 6px 16px rgba(16,185,129,.45); }
    .brand small { display:block; font-weight:400; font-size:.66rem; color:var(--mut); }
    .status { display:flex; align-items:center; gap:7px; font-size:.74rem; color:var(--mut);
              border:1px solid var(--line2); border-radius:999px; padding:4px 11px;
              background:var(--panel); }
    .live { width:7px; height:7px; border-radius:50%; background:var(--green);
            box-shadow:0 0 0 0 rgba(52,211,153,.6); animation:pulse 2s infinite; }
    @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(52,211,153,.5)} 70%{box-shadow:0 0 0 6px rgba(52,211,153,0)} 100%{box-shadow:0 0 0 0 rgba(52,211,153,0)} }

    /* KPIs inline in the topbar */
    .kpis { display:flex; gap:10px; margin-left:auto; align-items:stretch; }
    .kpi { background:linear-gradient(180deg, var(--panel2), var(--panel));
           border:1px solid var(--line); border-radius:12px;
           padding:7px 13px; min-width:118px; box-shadow:0 6px 18px -12px rgba(0,0,0,.6); }
    .kpi .lbl { font-size:.6rem; text-transform:uppercase; letter-spacing:.5px; color:var(--mut2); }
    .kpi .val { font-size:1.12rem; font-weight:700; line-height:1.15; margin-top:1px; }
    .kpi .val small { font-size:.68rem; font-weight:500; color:var(--mut); }
    .kpi.co2 .val { color:var(--green); } .kpi.cash .val { color:var(--cash); }
    .kpi.accrue .val { color:var(--brand2); font-variant-numeric:tabular-nums; }
    .kpi.accrue .lbl { color:var(--brand2); }

    /* live grid pill */
    .grid-pill { display:flex; align-items:center; gap:6px; font-size:.72rem; color:var(--mut);
                 border:1px solid var(--line2); border-radius:999px; padding:4px 12px;
                 background:var(--panel); white-space:nowrap; }
    .grid-pill b { color:var(--txt); font-weight:700; }
    .grid-pill .gi-sep { color:var(--mut2); }
    .grid-pill .gi-dot { width:8px; height:8px; border-radius:50%; background:var(--amber); }
    .grid-pill.clean .gi-dot { background:var(--green); }
    .grid-pill.dirty .gi-dot { background:var(--red); }

    /* value-changed flash */
    @keyframes flash { 0%{background:rgba(45,212,191,.30)} 100%{background:transparent} }
    .flash { animation:flash 1s ease-out; border-radius:6px; }

    .chips { display:flex; gap:5px; margin-top:3px; }
    .chip { font-size:.62rem; padding:1px 6px; border-radius:999px; font-weight:600;
            display:flex; align-items:center; gap:4px; }
    .chip .d { width:6px; height:6px; border-radius:50%; }
    .chip.g{background:rgba(52,211,153,.12);color:var(--green)}
    .chip.a{background:rgba(251,191,36,.12);color:var(--amber)}
    .chip.r{background:rgba(248,113,113,.12);color:var(--red)}
    .chip.g .d{background:var(--green)} .chip.a .d{background:var(--amber)} .chip.r .d{background:var(--red)}

    .toggle { display:flex; gap:6px; }
    .toggle a { text-decoration:none; font-size:.72rem; padding:5px 11px; border-radius:8px;
                border:1px solid var(--line2); color:var(--mut); background:var(--panel); font-weight:600; }
    .toggle a.on { background:var(--brand); border-color:var(--brand); color:#fff; }
    .sim-tag { font-size:.56rem; font-weight:800; letter-spacing:.5px; color:#fff; background:var(--red);
               border-radius:5px; padding:1px 6px; margin-left:4px; }

    /* ---- time-window picker ---- */
    .timepick { display:flex; align-items:center; gap:6px; font-size:.72rem; color:var(--mut);
                border:1px solid var(--line2); border-radius:999px; padding:3px 6px 3px 11px;
                background:var(--panel); white-space:nowrap; }
    .timepick .tp-ico { color:var(--brand2); }
    .timepick select, .timepick input {
        background:#000; border:1px solid var(--line2); color:var(--txt);
        border-radius:7px; padding:3px 6px; font-size:.7rem; font-family:inherit; }
    .timepick input[type="datetime-local"] { color-scheme:dark; }
    .timepick .tp-live { font-size:.58rem; font-weight:700; color:var(--green);
                         background:rgba(52,211,153,.12); border-radius:5px; padding:1px 6px; }
    .timepick .tp-now { text-decoration:none; font-size:.66rem; font-weight:700; color:#6ee7b7;
                        border:1px solid rgba(16,185,129,.4); background:rgba(16,185,129,.08);
                        border-radius:7px; padding:3px 8px; }
    .timepick .tp-now:hover { background:rgba(16,185,129,.18); }

    /* ---- board: fills remaining viewport ---- */
    .board { flex:1 1 auto; display:grid; gap:10px; padding:10px 14px;
             grid-template-columns: repeat(4, 1fr);
             grid-template-rows: minmax(0,1fr) minmax(0,.92fr) minmax(0,1.04fr);
             min-height:0; }

    .sec { background:linear-gradient(180deg, var(--panel2), var(--panel));
           border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow);
           display:flex; flex-direction:column; min-height:0; overflow:hidden; }
    .sec-head { display:flex; align-items:center; gap:9px; padding:9px 12px;
                border-bottom:1px solid var(--line); flex:0 0 auto; }
    .sec-ico { width:28px; height:28px; border-radius:9px; display:grid; place-items:center;
               background:var(--accent-soft); border:1px solid rgba(45,212,191,.28); font-size:.9rem; }
    .sec-title { font-weight:600; font-size:.86rem; }
    .sec-sub { font-size:.62rem; color:var(--mut2); margin-top:1px;
               max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .sec-tot { margin-left:auto; text-align:right; }
    .sec-tot .k { color:var(--green); font-weight:700; font-size:.9rem; }
    .sec-tot .c { color:var(--cash); font-weight:600; font-size:.68rem; }
    .rows { flex:1 1 auto; overflow:auto; padding:3px 6px; min-height:0; }
    .rows::-webkit-scrollbar{width:6px} .rows::-webkit-scrollbar-thumb{background:var(--line2);border-radius:3px}
    .row { display:grid; grid-template-columns: 8px 1fr auto; gap:9px;
           align-items:center; padding:6px 6px; border-radius:8px; }
    .row + .row { border-top:1px solid var(--line); }
    .row.revised { background:rgba(251,191,36,.05); }
    .dot { width:8px; height:8px; border-radius:50%; }
    .green{background:var(--green)} .amber{background:var(--amber)} .red{background:var(--red)}
    .r-name { font-weight:600; font-size:.78rem; line-height:1.2;
              overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .r-meta { font-size:.66rem; color:var(--mut); margin-top:2px; line-height:1.3;
              overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:230px; }
    .rev { font-size:.58rem; font-weight:700; color:var(--amber); background:rgba(251,191,36,.12);
           border:1px solid rgba(251,191,36,.3); border-radius:5px; padding:0 5px; margin-left:3px; }
    .rev.ai { color:#99f6e4; background:rgba(45,212,191,.14); border-color:rgba(45,212,191,.45); }
    .rev.over { color:#fecaca; background:rgba(248,113,113,.14); border-color:rgba(248,113,113,.5); }
    .rev.new { color:#bfdbfe; background:rgba(59,130,246,.20); border-color:rgba(96,165,250,.7); }
    .rev-note { color:var(--amber); }
    .rev-note.over { color:#f87171; }
    .portal-link { font-size:.66rem; font-weight:600; color:#6ee7b7; text-decoration:none;
                   border:1px solid rgba(16,185,129,.4); background:rgba(16,185,129,.08);
                   border-radius:8px; padding:5px 10px; white-space:nowrap; }
    .portal-link:hover { background:rgba(16,185,129,.16); }
    .r-save { text-align:right; white-space:nowrap; }
    .r-save .k { font-weight:700; font-size:.82rem; }
    .r-save .k.pos{color:var(--green)} .r-save .k.zero{color:var(--mut2)}
    .r-save .pct { font-size:.6rem; color:var(--mut2); }
    .r-save .c { color:var(--cash); font-size:.68rem; font-weight:600; margin-top:1px; }

    /* ---- agents tile (verdict + pipeline + transcript) ---- */
    .agents { grid-column: span 4;
              background:linear-gradient(180deg, var(--panel2), var(--panel));
              border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow);
              display:flex; flex-direction:column; min-height:0; overflow:hidden; }
    .agents .sec-head .sec-title { font-size:.86rem; }
    .nego-badge { margin-left:auto; font-size:.62rem; color:var(--amber);
                  background:rgba(251,191,36,.1); border:1px solid rgba(251,191,36,.3);
                  border-radius:999px; padding:2px 8px; font-weight:600; }
    .verdict { margin:8px 10px 6px; border-radius:9px; padding:8px 11px; font-size:.72rem;
               font-weight:600; border:1px solid; line-height:1.4; flex:0 0 auto; }
    .verdict.ok { background:rgba(52,211,153,.08); border-color:rgba(52,211,153,.4); color:#a7f3d0; }
    .verdict.blocked { background:rgba(248,113,113,.08); border-color:rgba(248,113,113,.45); color:#fecaca; }
    .pipe { display:flex; flex-wrap:wrap; gap:4px; align-items:center; padding:0 10px 8px;
            flex:0 0 auto; }
    .node { background:var(--panel2); border:1px solid var(--line2); border-radius:6px;
            padding:2px 7px; font-size:.6rem; font-weight:500; white-space:nowrap; }
    .node.llm { border-color:rgba(45,212,191,.5); color:#a7f3d0;
                background:rgba(16,185,129,.08); }
    .node.orch { border-color:var(--brand); color:#6ee7b7; font-weight:700;
                 background:linear-gradient(180deg, rgba(16,185,129,.18), rgba(45,212,191,.08));
                 box-shadow:0 0 0 1px rgba(16,185,129,.25) inset; }
    .orch-arm { color:var(--brand2); font-size:.55rem; font-weight:700; }
    .sep { color:var(--mut2); font-size:.55rem; }
    .tx { list-style:none; margin:0; padding:4px 10px 8px; overflow:auto; flex:1 1 auto; min-height:0; }
    .tx::-webkit-scrollbar{width:6px} .tx::-webkit-scrollbar-thumb{background:var(--line2);border-radius:3px}
    .tx li { font-size:.66rem; padding:5px 0; border-bottom:1px solid var(--line); line-height:1.4; }
    .tx li:last-child{border-bottom:none}
    .tx .hop { font-weight:600; color:#5eead4; }
    .tx .intent { color:var(--mut2); font-size:.6rem; }
    .tx li.nego { border-left:2px solid var(--amber); padding-left:8px;
                  background:rgba(251,191,36,.05); border-radius:0 6px 6px 0; }
    .tx li.nego .hop { color:var(--amber); }

    /* ---- plain-English summary panel (spans full width, below agents) ---- */
    .summary { grid-column: span 4;
               background:linear-gradient(180deg, var(--panel2), var(--panel));
               border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow);
               display:flex; flex-direction:column; min-height:0; overflow:hidden; }
    .sum-grid { flex:1 1 auto; overflow:hidden; display:grid; gap:10px; padding:9px 12px;
                grid-template-columns: repeat(4, 1fr); min-height:0; }
    .sum-grid::-webkit-scrollbar{width:6px} .sum-grid::-webkit-scrollbar-thumb{background:var(--line2);border-radius:3px}
    .sum-col { background:var(--panel); border:1px solid var(--line); border-radius:11px;
               padding:9px 11px; display:flex; flex-direction:column; min-height:0; overflow:hidden; }
    .sum-h { font-weight:700; font-size:.76rem; display:flex; align-items:center; gap:6px; flex:0 0 auto; }
    .sum-h .sum-ico { font-size:.92rem; }
    .sum-tot { margin-left:auto; font-size:.6rem; font-weight:700; color:var(--green); white-space:nowrap; }
    .sum-intro { font-size:.64rem; color:var(--mut); margin:5px 0 7px; line-height:1.45; flex:0 0 auto; }
    .sum-list { list-style:none; margin:0; padding:0 4px 0 0; display:flex; flex-direction:column; gap:6px;
                flex:1 1 auto; overflow-y:auto; min-height:0; }
    .sum-list::-webkit-scrollbar{width:6px} .sum-list::-webkit-scrollbar-thumb{background:var(--line2);border-radius:3px}
    .sum-list li { font-size:.66rem; line-height:1.42; color:var(--txt);
                   padding-left:14px; position:relative; }
    .sum-list li::before { content:"•"; position:absolute; left:1px; color:var(--mut2); }
    .sum-list li.ai::before { content:"✦"; color:#5eead4; }
    .sum-list li.ov::before { content:"⚑"; color:#f87171; }
    .sum-list li b { font-weight:700; }
    .sum-empty { font-size:.64rem; color:var(--mut2); font-style:italic; }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand">
      <span class="logo">⚡</span>
      <span>CarbonShift<small>Organizational Sustainability Co-Pilot</small></span>
    </div>
    <div class="grid-pill {{ 'clean' if grid.cleaner else 'dirty' }}" id="gridPill" title="Live UK grid carbon intensity (updates every 30 min)">
      <span class="gi-dot"></span>
      Grid <b id="gridNow">{{ grid.now }}</b> gCO₂/kWh ·
      <span id="gridTrend">{{ 'cleaner' if grid.cleaner else 'dirtier' }} than 24h avg</span>
      <span class="gi-sep">·</span> greenest <b id="gridGreenAt">{{ grid.greenest_at }}</b>
      (<span id="gridGreenVal">{{ grid.greenest_val }}</span> g)
      <span class="sim-tag" id="simTag" hidden>SIMULATED</span>
    </div>
    <div class="status"><span class="live"></span><span id="updated">live · updated just now</span></div>
    <div class="timepick" title="Choose the window and the moment the dashboard is evaluated 'as of'. Defaults to the last 24 hours, live.">
      <span class="tp-ico">🕑</span>
      <select id="winSel">
        {% for k, w in windows %}
        <option value="{{ k }}"{{ ' selected' if k == window else '' }}>{{ w }}</option>
        {% endfor %}
      </select>
      <span>ending</span>
      <input type="datetime-local" id="atInput" value="{{ as_of_iso }}">
      {% if is_live %}<span class="tp-live">● LIVE</span>{% else %}<a class="tp-now" href="#" id="tpNow">Now</a>{% endif %}
    </div>
    <div class="kpis">
      <div class="kpi co2">
        <div class="lbl">CO₂ avoided / yr</div>
        <div class="val" id="kCo2">{{ "%.1f"|format(total_kg/1000.0) }} <small>t</small></div>
      </div>
      <div class="kpi cash">
        <div class="lbl">Cost saved / yr</div>
        <div class="val" id="kCash">{{ sym }}{{ "{:,.0f}".format(total_money) }}</div>
      </div>
      <div class="kpi accrue" title="Projected savings accruing since midnight at the estimated annual rate — illustrative, only realised if the recommendations are enacted.">
        <div class="lbl">Accruing today ⓘ</div>
        <div class="val"><span id="accrueKg">0.0</span><small> kg</small> · <span id="accrueCash">{{ sym }}0</span></div>
      </div>
      <div class="kpi">
        <div class="lbl">Recommendations</div>
        <div class="chips">
          <span class="chip g"><span class="d"></span><span id="cGreen">{{ risk_counts.green }}</span></span>
          <span class="chip a"><span class="d"></span><span id="cAmber">{{ risk_counts.amber }}</span></span>
          <span class="chip r"><span class="d"></span><span id="cRed">{{ risk_counts.red }}</span></span>
        </div>
      </div>
      <a class="portal-link" href="/request" title="Open the request portal (compute, travel, fleet, procurement)">➕ Request portal</a>
    </div>
  </div>

  <div class="board">
    {% for s in sections %}
    <section class="sec" data-key="{{ s.key }}">
      <div class="sec-head">
        <div class="sec-ico">{{ s.icon }}</div>
        <div>
          <div class="sec-title">{{ s.title }}</div>
          <div class="sec-sub">{{ s.count }} item{{ '' if s.count == 1 else 's' }} · {{ s.cadence }}</div>
        </div>
        <div class="sec-tot" data-sec="{{ s.key }}">
          <div class="k">{{ "%.0f"|format(s.sub_kg) }}{{ s.unit }}</div>
          <div class="c">{{ sym }}{{ "%.0f"|format(s.sub_money) }}</div>
        </div>
      </div>
      <div class="rows">
        {% for r in s.rows %}
        <div class="row {{ 'revised' if r.revised else '' }}">
          <span class="dot {{ r.risk }}"></span>
          <div>
            <div class="r-name">{{ r.name }}{% if r.new %} <span class="rev new">🆕 NEW</span>{% endif %}{% if r.ai %} <span class="rev ai">✦ AI</span>{% elif r.revised %} <span class="rev">⇄</span>{% endif %}{% if r.manager_override %} <span class="rev over">⚑ Manager override</span>{% endif %}</div>
            <div class="r-meta">{{ r.meta }}{% if r.revised %} · <span class="rev-note">{{ r.revised_note }}</span>{% endif %}{% if r.manager_override %} · <span class="rev-note over">{{ r.override_reason }}</span>{% endif %}</div>
          </div>
          <div class="r-save">
            <span class="k {{ 'pos' if r.kg > 0 else 'zero' }}">{{ "%.1f"|format(r.kg) }}{{ s.unit }}</span>
            <span class="pct">· {{ "%.0f"|format(r.pct) }}%</span>
            <div class="c">{{ sym }}{{ "%.0f"|format(r.money) }}</div>
          </div>
        </div>
        {% endfor %}
      </div>
    </section>
    {% endfor %}

    <section class="agents">
      <div class="sec-head">
        <div class="sec-ico">🤝</div>
        <div class="sec-title">Agent team · {{ pipeline|length }} agents · orchestrated</div>
        <span class="nego-badge" id="negoBadge"{% if negotiation_rounds == 0 %} hidden{% endif %}>⇄ {{ negotiation_rounds }} negotiation round{{ '' if negotiation_rounds == 1 else 's' }}</span>
      </div>
      <div class="verdict {{ 'ok' if risk_ok else 'blocked' }}" id="verdict">{{ risk_verdict }}</div>
      <div class="pipe">
        <span class="node orch" title="The Orchestrator coordinates the agent team over a shared blackboard and runs the RiskAgent review/negotiation loop.">⚙ Orchestrator</span>
        <span class="orch-arm">⟜</span>
        {% for n in pipeline %}
          <span class="node {{ 'llm' if n == 'BriefingAgent' else '' }}">{{ n }}</span>
          {% if not loop.last %}<span class="sep">→</span>{% endif %}
        {% endfor %}
      </div>
      <ul class="tx" id="txList">
        {% for m in transcript %}
        <li class="{{ 'nego' if 'revis' in m.intent else '' }}">
          <span class="hop">{{ m.sender }} → {{ m.recipient }}</span>
          <span class="intent">[{{ m.intent }}]</span><br>{{ m.summary }}
        </li>
        {% endfor %}
      </ul>
    </section>

    <section class="summary">
      <div class="sec-head">
        <div class="sec-ico">📋</div>
        <div class="sec-title">In plain English · what was requested &amp; what the agents did about it</div>
      </div>
      <div class="sum-grid">
        {% for d in summary %}
        <div class="sum-col">
          <div class="sum-h"><span class="sum-ico">{{ d.icon }}</span> {{ d.title }}
            <span class="sum-tot">{{ "%.0f"|format(d.kg) }} kg · {{ sym }}{{ "%.0f"|format(d.money) }}</span>
          </div>
          <div class="sum-intro">{{ d.intro }}</div>
          {% if d.lines %}
          <ul class="sum-list">
            {% for it in d.lines %}
            <li class="{{ 'ov' if it.override else ('ai' if it.ai else '') }}">{{ it.text|safe }}</li>
            {% endfor %}
          </ul>
          {% else %}
          <div class="sum-empty">No requests in this category yet.</div>
          {% endif %}
        </div>
        {% endfor %}
      </div>
    </section>
  </div>

  <script>
    const CFG = {
      scenario: {{ scenario|tojson }},
      sym: {{ sym|tojson }},
      annualKg: {{ total_kg|tojson }},
      annualCash: {{ total_money|tojson }},
      dataVersion: {{ data_version|tojson }},
      win: {{ window|tojson }},
      at: {{ as_of_iso|tojson }},
      isLive: {{ is_live|tojson }},
    };
    const SECONDS_PER_YEAR = 365 * 24 * 3600;
    let rateKg = CFG.annualKg / SECONDS_PER_YEAR;
    let rateCash = CFG.annualCash / SECONDS_PER_YEAR;

    const fmtMoney = n => CFG.sym + Math.round(n).toLocaleString();
    const $ = id => document.getElementById(id);

    function setVal(el, text) {
      if (!el || el.textContent === text) return;
      el.textContent = text;
      el.classList.remove("flash");
      void el.offsetWidth;            // restart animation
      el.classList.add("flash");
    }

    // --- live "accruing today" ticker (projection since local midnight) ---
    function secondsSinceMidnight() {
      const now = new Date();
      const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      return (now - midnight) / 1000;
    }
    function tick() {
      const el = secondsSinceMidnight();
      $("accrueKg").textContent = (rateKg * el).toFixed(1);
      $("accrueCash").textContent = CFG.sym + (rateCash * el).toFixed(2);
    }
    setInterval(tick, 250);
    tick();

    // --- time-window picker: reload the dashboard for the chosen window / moment ---
    function applyTimeWindow(useNow) {
      const params = new URLSearchParams(window.location.search);
      params.set("scenario", CFG.scenario);
      params.set("win", document.getElementById("winSel").value);
      if (useNow) {
        params.delete("at");                       // back to live (now)
      } else {
        params.set("at", document.getElementById("atInput").value);
      }
      window.location.search = params.toString();
    }
    const winSel = document.getElementById("winSel");
    const atInput = document.getElementById("atInput");
    if (winSel) winSel.addEventListener("change", () => applyTimeWindow(CFG.isLive));
    if (atInput) atInput.addEventListener("change", () => applyTimeWindow(false));
    const tpNow = document.getElementById("tpNow");
    if (tpNow) tpNow.addEventListener("click", (e) => { e.preventDefault(); applyTimeWindow(true); });

    // --- poll the pipeline for live grid + savings changes ---
    let lastPoll = Date.now();

    function ago() {
      const s = Math.round((Date.now() - lastPoll) / 1000);
      $("updated").textContent = s < 2 ? "live · updated just now" : `live · updated ${s}s ago`;
    }
    setInterval(ago, 1000);

    async function refresh() {
      try {
        let url = "/api/state?scenario=" + encodeURIComponent(CFG.scenario)
                + "&win=" + encodeURIComponent(CFG.win);
        if (!CFG.isLive) url += "&at=" + encodeURIComponent(CFG.at);
        const r = await fetch(url, {cache: "no-store"});
        const d = await r.json();
        lastPoll = Date.now();

        rateKg = d.total_kg / SECONDS_PER_YEAR;
        rateCash = d.total_money / SECONDS_PER_YEAR;
        const co2t = (d.total_kg / 1000).toFixed(1);
        const co2El = $("kCo2");
        if (co2El.dataset.v !== co2t) {
          co2El.dataset.v = co2t;
          co2El.innerHTML = co2t + ' <small>t</small>';
          co2El.classList.remove("flash"); void co2El.offsetWidth; co2El.classList.add("flash");
        }
        setVal($("kCash"), fmtMoney(d.total_money));

        setVal($("cGreen"), String(d.risk_counts.green));
        setVal($("cAmber"), String(d.risk_counts.amber));
        setVal($("cRed"), String(d.risk_counts.red));

        // live grid
        const g = d.grid;
        setVal($("gridNow"), String(g.now));
        setVal($("gridTrend"), (g.cleaner ? "cleaner" : "dirtier") + " than 24h avg");
        setVal($("gridGreenAt"), g.greenest_at);
        setVal($("gridGreenVal"), String(g.greenest_val));
        const pill = $("gridPill");
        pill.classList.toggle("clean", g.cleaner);
        pill.classList.toggle("dirty", !g.cleaner);
        $("simTag").hidden = !g.simulated;

        // per-domain subtotals
        d.sections.forEach(s => {
          const box = document.querySelector('[data-sec="' + s.key + '"]');
          if (!box) return;
          setVal(box.querySelector(".k"), Math.round(s.sub_kg) + s.unit);
          setVal(box.querySelector(".c"), fmtMoney(s.sub_money));
        });

        // --- live data dump detected: re-render rows + agent transcript in place ---
        if (d.data_version && d.data_version !== CFG.dataVersion) {
          CFG.dataVersion = d.data_version;
          d.sections.forEach(s => {
            const sec = document.querySelector('.sec[data-key="' + s.key + '"]');
            if (!sec) return;
            const rowsBox = sec.querySelector(".rows");
            if (rowsBox && s.rows_html != null) {
              rowsBox.innerHTML = s.rows_html;
              rowsBox.classList.remove("flash"); void rowsBox.offsetWidth; rowsBox.classList.add("flash");
            }
            const sub = sec.querySelector(".sec-sub");
            if (sub) sub.textContent = s.count + " item" + (s.count === 1 ? "" : "s") + " · " + s.cadence;
          });
          const tx = $("txList");
          if (tx && d.transcript_html != null) tx.innerHTML = d.transcript_html;
          const verdict = $("verdict");
          if (verdict) {
            verdict.textContent = d.risk_verdict;
            verdict.classList.toggle("ok", d.risk_ok);
            verdict.classList.toggle("blocked", !d.risk_ok);
          }
          const nego = $("negoBadge");
          if (nego) {
            nego.hidden = !(d.negotiation_rounds > 0);
            nego.textContent = "⇄ " + d.negotiation_rounds + " negotiation round" + (d.negotiation_rounds === 1 ? "" : "s");
          }
        }
      } catch (e) { /* keep last good values on transient errors */ }
    }
    setInterval(refresh, 30000);   // grid forecast updates every 30 min; poll often enough to catch it

    // --- fast demo-feed watcher: detect a data dump within seconds and re-plan ---
    async function watchData() {
      try {
        const r = await fetch("/api/version", {cache: "no-store"});
        const v = (await r.json()).data_version;
        if (v && v !== CFG.dataVersion) refresh();   // pulls full state + re-renders
      } catch (e) { /* ignore transient errors */ }
    }
    setInterval(watchData, 3000);
    // Background tabs throttle timers; re-check the instant the tab regains focus
    // so a data dump made while the dashboard was hidden shows immediately.
    document.addEventListener("visibilitychange", () => { if (!document.hidden) watchData(); });
    window.addEventListener("focus", watchData);
  </script>
</body>
</html>
"""


# Row + transcript fragments, reused by /api/state so the live re-render shares the
# exact markup the full page renders server-side (single source of truth).
SECTION_ROWS_TPL = """{% for r in rows %}
<div class="row {{ 'revised' if r.revised else '' }}">
  <span class="dot {{ r.risk }}"></span>
  <div>
    <div class="r-name">{{ r.name }}{% if r.new %} <span class="rev new">🆕 NEW</span>{% endif %}{% if r.ai %} <span class="rev ai">✦ AI</span>{% elif r.revised %} <span class="rev">⇄</span>{% endif %}{% if r.manager_override %} <span class="rev over">⚑ Manager override</span>{% endif %}</div>
    <div class="r-meta">{{ r.meta }}{% if r.revised %} · <span class="rev-note">{{ r.revised_note }}</span>{% endif %}{% if r.manager_override %} · <span class="rev-note over">{{ r.override_reason }}</span>{% endif %}</div>
  </div>
  <div class="r-save">
    <span class="k {{ 'pos' if r.kg > 0 else 'zero' }}">{{ "%.1f"|format(r.kg) }}{{ unit }}</span>
    <span class="pct">· {{ "%.0f"|format(r.pct) }}%</span>
    <div class="c">{{ sym }}{{ "%.0f"|format(r.money) }}</div>
  </div>
</div>
{% endfor %}"""

TRANSCRIPT_TPL = """{% for m in transcript %}
<li class="{{ 'nego' if 'revis' in m.intent else '' }}">
  <span class="hop">{{ m.sender }} → {{ m.recipient }}</span>
  <span class="intent">[{{ m.intent }}]</span><br>{{ m.summary }}
</li>
{% endfor %}"""


def _grid_snapshot(forecast, now):
    """Current grid intensity and the greenest upcoming window from the live forecast."""
    pts = forecast.points
    current = next(
        (g for (s, e, g) in pts if s <= now < e),
        pts[0][2] if pts else 0.0,
    )
    upcoming = [(s, g) for (s, e, g) in pts if e > now][:48]  # next ~24h
    if upcoming:
        g_start, g_val = min(upcoming, key=lambda x: x[1])
        vals = [g for _, g in upcoming]
        avg = sum(vals) / len(vals)
    else:
        g_start, g_val, avg = now, current, current
    return {
        "now": round(current),
        "avg": round(avg),
        "cleaner": current <= avg,
        "greenest_val": round(g_val),
        "greenest_at": g_start.strftime("%a %H:%M"),
        "source": "live grid" if "carbonintensity" in forecast.source else "synthetic",
        "simulated": "simulated-spike" in forecast.source,
    }


def _build_state(scenario, spike=0.0, as_of=None, window="24h"):
    """Run the full pipeline and assemble every value the dashboard renders."""
    if scenario not in SCENARIOS:
        scenario = "relaxed"
    if window not in _WINDOWS:
        window = "24h"
    now = as_of or datetime.now(timezone.utc)
    job_src = get_jobs(scenario=scenario, now=now)
    trip_src = get_trips()
    # Backend-driven grid-stress event: if no explicit spike was requested, use the
    # value set in the injection file (a demo script can trigger a live re-plan).
    if spike <= 0.0:
        spike = injected_spike()
    # Live demo feed: append any data dumped into demo_inject.json so newly-added
    # jobs/purchases/vehicles/trips flow straight through the agent pipeline.
    injected = load_injected(now=now)
    # Names of freshly-injected items, so the dashboard can badge them as NEW and the
    # audience can instantly spot data the agents have just picked up (all 4 domains).
    injected_names = {
        o.name
        for o in (
            injected["jobs"]
            + injected["trips"]
            + injected["vehicles"]
            + injected["purchases"]
        )
    }
    # Unified request portal: decided requests (all domains) flow onto the dashboard.
    mgr = requests_store.dashboard_feed()
    bb = _DASHBOARD.run(
        job_src.jobs + injected["jobs"] + mgr.jobs,
        trips=trip_src.trips + injected["trips"] + mgr.trips,
        now=now,
        trip_source=trip_src.source,
        job_source=job_src.source,
        vehicles=demo_vehicles() + injected["vehicles"] + mgr.vehicles,
        purchases=demo_purchases() + injected["purchases"] + mgr.purchases,
        grid_spike=spike,
    )
    plan = bb.plan
    travel = bb.travel_plan

    compute_rows = [
        {
            "name": d.job.name,
            "risk": d.risk.value,
            "meta": f"run {d.chosen_start:%a %H:%M} UTC (baseline {d.baseline_start:%a %H:%M}) · "
            f"{d.baseline_intensity:.0f} → {d.chosen_intensity:.0f} gCO₂/kWh · "
            f"deadline {d.job.deadline:%a %H:%M}",
            "kg": d.kg_co2_saved,
            "pct": d.pct_saved,
            "money": d.money_saved,
            "revised": (
                bb.applied_safety_buffer_hours > 0.0
                and d.chosen_start != d.baseline_start
            ),
            "revised_note": f"+{bb.applied_safety_buffer_hours * 60:.0f}-min safety buffer",
            "manager_override": d.job.name in mgr.override_reasons,
            "override_reason": mgr.override_reasons.get(d.job.name, ""),
            "new": d.job.name in injected_names,
        }
        for d in plan.decisions
    ]
    travel_rows = [
        {
            "name": t.trip.name,
            "risk": t.risk.value,
            "meta": f"{t.baseline_mode.value} → {t.chosen_mode.value} · "
            f"{t.trip.distance_km:.0f} km"
            + (f" · ✦ {t.classification_note}" if t.classification_note else ""),
            "kg": t.kg_co2_saved,
            "pct": t.pct_saved,
            "money": t.money_saved,
            "ai": getattr(t, "ai_classified", False),
            "manager_override": t.trip.name in mgr.override_reasons,
            "override_reason": mgr.override_reasons.get(t.trip.name, ""),
            "revised": t.trip.name in bb.keep_physical_trips,
            "revised_note": "kept in person per travel policy",
            "new": t.trip.name in injected_names,
        }
        for t in travel.decisions
    ]

    def _measure_rows(mplan):
        return [
            {
                "name": m.name,
                "risk": m.risk.value,
                "meta": m.action + (f" · {m.detail}" if getattr(m, "detail", "") else ""),
                "kg": m.kg_co2_saved,
                "pct": m.pct_saved,
                "money": m.money_saved,
                "revised": getattr(m, "ai_proposed", False),
                "revised_note": "agent-selected best option" if getattr(m, "ai_proposed", False) else "",
                "ai": getattr(m, "ai_proposed", False),
                "manager_override": m.name in mgr.override_reasons,
                "override_reason": mgr.override_reasons.get(m.name, ""),
                "new": m.name in injected_names,
            }
            for m in (mplan.decisions if mplan else [])
        ]

    def _section(key, title, icon, unit, cadence, source, rows):
        return {
            "key": key,
            "title": title,
            "icon": icon,
            "unit": unit,
            "cadence": cadence,
            "source": source,
            "rows": rows,
            "count": len(rows),
            "sub_kg": sum(r["kg"] for r in rows),
            "sub_money": sum(r["money"] for r in rows),
        }

    sections = [
        _section("compute", "Compute workloads", "⚡", " kg", "per shift",
                 bb.job_source, compute_rows),
        _section("travel", "Business travel", "✈", " kg", "per cycle",
                 bb.trip_source, travel_rows),
        _section("fleet", "Fleet", "🚚", " kg", "per year",
                 None, _measure_rows(bb.fleet_plan)),
        _section("procurement", "Procurement", "📦", " kg", "per year",
                 None, _measure_rows(bb.procurement_plan)),
    ]

    # Plain-English summary: one column per domain, describing each request case
    # and what the agents decided, in language anyone can follow.
    _SUMMARY_INTRO = {
        "compute": "Computing jobs people asked to run. The agents move each one into "
                   "the cleanest electricity window before its deadline.",
        "travel": "Trips people requested. The agents check whether travelling is really "
                  "needed and pick the lowest-carbon way to go.",
        "fleet": "Delivery vehicles and routes (mostly pulled in automatically from "
                 "courier data). The agents find which can switch to electric or cleaner fuel.",
        "procurement": "Things the business buys. The agents find a lower-carbon "
                       "alternative for each item.",
    }

    def _plain(row, unit):
        saved = f"~{row['kg']:.0f}{unit} CO\u2082"
        if row["money"] > 0:
            saved += f" and {CURRENCY_SYMBOL}{row['money']:.0f}"
        if row.get("manager_override"):
            reason = row.get("override_reason") or ""
            tail = f" — but it was kept as the original choice on request" + (
                f": “{reason}”." if reason else "."
            )
            text = f"<b>{row['name']}</b>: the greener option would save {saved}{tail}"
        else:
            text = f"<b>{row['name']}</b>: {row['meta']} — saves {saved}."
        return {
            "text": text,
            "ai": row.get("ai", False),
            "override": row.get("manager_override", False),
        }

    summary = [
        {
            "key": s["key"],
            "title": s["title"],
            "icon": s["icon"],
            "intro": _SUMMARY_INTRO.get(s["key"], ""),
            "kg": s["sub_kg"],
            "money": s["sub_money"],
            "lines": [_plain(r, s["unit"]) for r in s["rows"]],
        }
        for s in sections
    ]

    all_rows = compute_rows + travel_rows
    for s in sections[2:]:
        all_rows += s["rows"]
    risk_counts = {
        "green": sum(1 for r in all_rows if r["risk"] == "green"),
        "amber": sum(1 for r in all_rows if r["risk"] == "amber"),
        "red": sum(1 for r in all_rows if r["risk"] == "red"),
    }

    pipeline = [
        "ForecastAgent", "OptimizerAgent", "TravelAgent",
        "FleetAgent", "ProcurementAgent", "RiskAgent", "CostAgent", "BriefingAgent",
    ]

    return {
        "scenario": scenario,
        "sym": CURRENCY_SYMBOL,
        "forecast_source": bb.forecast.source,
        "confidence": bb.forecast_confidence,
        "risk_verdict": bb.risk_verdict,
        "risk_ok": bb.risk_ok,
        "transcript": bb.transcript,
        "total_kg": bb.total_kg_saved,
        "total_money": bb.total_money_saved,
        "sections": sections,
        "summary": summary,
        "risk_counts": risk_counts,
        "pipeline": pipeline,
        "negotiation_rounds": bb.negotiation_rounds,
        "grid": _grid_snapshot(bb.forecast, now),
        "spike": spike,
        "data_version": _feed_version(),
        "window": window,
        "window_label": _WINDOWS[window][0],
        "windows": [(k, v[0]) for k, v in _WINDOWS.items()],
        "as_of_iso": now.strftime("%Y-%m-%dT%H:%M"),
        "as_of_label": now.strftime("%d %b %Y · %H:%M UTC"),
        "is_live": as_of is None,
    }


@app.route("/")
def index():
    scenario = request.args.get("scenario", "relaxed")
    window = request.args.get("win", "24h")
    as_of = _parse_at(request.args.get("at"))
    state = _build_state(scenario, as_of=as_of, window=window)
    return render_template_string(PAGE, **state)


@app.route("/api/state")
def api_state():
    """Lightweight JSON snapshot for the dashboard's live auto-refresh.

    Includes pre-rendered row + transcript HTML so the page can re-render in place
    when the demo feed changes the underlying data — no full reload needed.
    """
    try:
        spike = max(0.0, float(request.args.get("spike", 0)))
    except ValueError:
        spike = 0.0
    state = _build_state(
        request.args.get("scenario", "relaxed"),
        spike=spike,
        as_of=_parse_at(request.args.get("at")),
        window=request.args.get("win", "24h"),
    )
    sym = state["sym"]
    return {
        "total_kg": state["total_kg"],
        "total_money": state["total_money"],
        "risk_counts": state["risk_counts"],
        "grid": state["grid"],
        "negotiation_rounds": state["negotiation_rounds"],
        "risk_ok": state["risk_ok"],
        "risk_verdict": state["risk_verdict"],
        "spike": spike,
        "data_version": state["data_version"],
        "transcript_html": render_template_string(
            TRANSCRIPT_TPL, transcript=state["transcript"]
        ),
        "sections": [
            {
                "key": s["key"],
                "sub_kg": s["sub_kg"],
                "sub_money": s["sub_money"],
                "unit": s["unit"],
                "count": s["count"],
                "cadence": s["cadence"],
                "rows_html": render_template_string(
                    SECTION_ROWS_TPL, rows=s["rows"], unit=s["unit"], sym=sym
                ),
            }
            for s in state["sections"]
        ],
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
    }


@app.route("/api/version")
def api_version():
    """Cheap fingerprint of the demo feed so the page can detect data dumps fast.

    Reads only file metadata (no pipeline run), so it is safe to poll every few
    seconds during a live demo.
    """
    return {"data_version": _feed_version()}


# --------------------------------------------------------------------------- #
# Manager travel-request portal (separate from the team dashboard)
# --------------------------------------------------------------------------- #
PORTAL_HEAD = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CarbonShift · Request Portal</title>
<style>
  :root { color-scheme: dark; --bg:#000000; --panel:#0a0a0a; --line:#1c241f;
    --txt:#e8f3ec; --mut:#8fb0a1; --brand:#10b981; --brand2:#2dd4bf;
    --green:#34d399; --amber:#fbbf24; --red:#f87171; --cash:#f5c451; }
  * { box-sizing:border-box; }
  body { font-family:'Inter','Segoe UI',system-ui,sans-serif; margin:0; color:var(--txt);
    background:radial-gradient(1100px 560px at 88% -12%, rgba(16,185,129,.12), transparent 60%), var(--bg);
    min-height:100vh; display:flex; align-items:flex-start; justify-content:center; padding:40px 16px; }
  .card { width:100%; max-width:620px; background:linear-gradient(180deg,#101211,#0a0a0a);
    border:1px solid var(--line); border-radius:16px; padding:28px 30px;
    box-shadow:0 20px 50px -20px rgba(0,0,0,.9); }
  .brand { display:flex; align-items:center; gap:10px; margin-bottom:4px; }
  .brand .logo { font-size:1.3rem; }
  .brand b { font-size:1.05rem; }
  .brand small { display:block; color:var(--mut); font-size:.66rem; font-weight:500; }
  h1 { font-size:1.15rem; margin:18px 0 4px; }
  .lead { color:var(--mut); font-size:.82rem; margin:0 0 20px; line-height:1.5; }
  label { display:block; font-size:.72rem; color:var(--mut); margin:14px 0 5px; font-weight:600; }
  input, select { width:100%; background:#000; border:1px solid var(--line); color:var(--txt);
    border-radius:9px; padding:10px 12px; font-size:.85rem; font-family:inherit; }
  input:focus, select:focus { outline:none; border-color:var(--brand); }
  .row2 { display:flex; gap:12px; } .row2 > div { flex:1; }
  .check { display:flex; align-items:center; gap:8px; margin-top:14px; }
  .check input { width:auto; }
  .btn { display:inline-block; border:none; cursor:pointer; font-family:inherit; font-weight:700;
    border-radius:10px; padding:11px 18px; font-size:.85rem; margin-top:22px; text-decoration:none; }
  .btn.go { background:linear-gradient(180deg,var(--brand),#0ea371); color:#04140d; width:100%; }
  .btn.accept { background:linear-gradient(180deg,var(--green),#0ea371); color:#04140d; }
  .btn.override { background:rgba(248,113,113,.14); border:1px solid rgba(248,113,113,.5); color:#fecaca; }
  .btn.ghost { background:transparent; border:1px solid var(--line); color:var(--mut); }
  .email { background:#000; border:1px solid var(--line); border-radius:12px; padding:18px 20px;
    margin:6px 0 18px; font-size:.82rem; line-height:1.6; }
  .email .hdr { color:var(--mut); font-size:.7rem; border-bottom:1px solid var(--line);
    padding-bottom:10px; margin-bottom:12px; }
  .email pre { white-space:pre-wrap; font-family:inherit; margin:0; }
  .pill { display:inline-block; font-size:.66rem; font-weight:700; border-radius:6px;
    padding:2px 8px; border:1px solid; }
  .pill.green { color:#a7f3d0; background:rgba(52,211,153,.1); border-color:rgba(52,211,153,.4); }
  .pill.amber { color:#fde68a; background:rgba(251,191,36,.1); border-color:rgba(251,191,36,.4); }
  .pill.red { color:#fecaca; background:rgba(248,113,113,.1); border-color:rgba(248,113,113,.45); }
  .actions { display:flex; gap:12px; flex-wrap:wrap; }
  .note { color:var(--mut); font-size:.72rem; line-height:1.5; margin-top:16px; }
  .ok-banner { background:rgba(52,211,153,.1); border:1px solid rgba(52,211,153,.4);
    color:#a7f3d0; border-radius:10px; padding:12px 14px; font-size:.82rem; line-height:1.5; }
  .over-banner { background:rgba(248,113,113,.1); border:1px solid rgba(248,113,113,.45);
    color:#fecaca; border-radius:10px; padding:12px 14px; font-size:.82rem; line-height:1.5; }
  .info-banner { background:rgba(45,212,191,.08); border:1px solid rgba(45,212,191,.3);
    color:#99f6e4; border-radius:10px; padding:11px 14px; font-size:.76rem; line-height:1.5; margin-bottom:16px; }
  textarea { width:100%; background:#000; border:1px solid var(--line); color:var(--txt);
    border-radius:9px; padding:10px 12px; font-size:.85rem; font-family:inherit; resize:vertical; }
  a.back { color:var(--brand2); font-size:.75rem; text-decoration:none; }
  .hub { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:4px; }
  .hub a { display:block; text-decoration:none; color:var(--txt); background:#000;
    border:1px solid var(--line); border-radius:12px; padding:16px 16px; transition:border-color .15s, background .15s; }
  .hub a:hover { border-color:var(--brand); background:rgba(16,185,129,.06); }
  .hub .ico { font-size:1.4rem; }
  .hub .t { font-weight:700; font-size:.92rem; margin:8px 0 3px; }
  .hub .d { color:var(--mut); font-size:.72rem; line-height:1.45; }
</style></head><body><div class="card">
  <div class="brand"><span class="logo">⚡</span>
    <span><b>CarbonShift</b><small>Request Portal</small></span></div>
"""
PORTAL_FOOT = "</div></body></html>"

REQUEST_HUB_TPL = PORTAL_HEAD + """
  <h1>Submit a request</h1>
  <p class="lead">Pick what you need. Our sustainability co-pilot reasons about the
    lowest-carbon way to fulfil it and emails you a recommendation you can accept or
    override. The carbon-reduction team sees the outcome on their dashboard.</p>
  <div class="hub">
    <a href="/request/compute">
      <div class="ico">⚡</div>
      <div class="t">Compute workload</div>
      <div class="d">Run a deferrable job — we shift it into the greenest grid window.</div>
    </a>
    <a href="/request/travel">
      <div class="ico">✈</div>
      <div class="t">Business travel</div>
      <div class="d">A trip request — we check if it needs in-person presence or can go virtual.</div>
    </a>
    <a href="/request/fleet">
      <div class="ico">🚚</div>
      <div class="t">Fleet vehicle</div>
      <div class="d">Mostly automatic from delivery/courier data — add a vehicle or route manually here.</div>
    </a>
    <a href="/request/procurement">
      <div class="ico">📦</div>
      <div class="t">Procurement</div>
      <div class="d">A purchased good/service — we propose a lower-carbon alternative.</div>
    </a>
  </div>
""" + PORTAL_FOOT

# Per-domain request forms. Each posts to /request/<domain>.
_FORM_IDENTITY = """
    <div class="row2">
      <div><label>Your name</label><input name="requester" required placeholder="Jane Doe"></div>
      <div><label>Your email</label><input name="email" type="email" required placeholder="jane@contoso.com"></div>
    </div>
"""

COMPUTE_FORM_TPL = PORTAL_HEAD + """
  <h1>⚡ Compute workload request</h1>
  <p class="lead">Submit a deferrable job. We schedule it into the cleanest grid window
    before your deadline; you can override to run it now.</p>
  <form method="post" action="/request/compute">
""" + _FORM_IDENTITY + """
    <label>Workload name</label>
    <input name="title" required placeholder="e.g. Nightly ML training run">
    <div class="row2">
      <div><label>Power draw (kW)</label><input name="power_kw" type="number" min="0.1" step="0.1" required placeholder="80"></div>
      <div><label>Duration (hours)</label><input name="duration_hours" type="number" min="0.1" step="0.1" required placeholder="3"></div>
    </div>
    <label>Deadline — finish within (hours)</label>
    <input name="due_in_hours" type="number" min="1" step="1" required placeholder="18">
    <button class="btn go" type="submit">Get recommendation →</button>
  </form>
  <p style="margin-top:16px"><a class="back" href="/request">← All request types</a></p>
""" + PORTAL_FOOT

TRAVEL_FORM_TPL = PORTAL_HEAD + """
  <h1>✈ Business travel request</h1>
  <p class="lead">Describe your trip in plain language. We reason about whether it needs
    your physical presence and recommend rail or a virtual meeting where it fits.</p>
  <form method="post" action="/request/travel">
""" + _FORM_IDENTITY + """
    <label>Trip purpose &amp; destination</label>
    <input name="title" required placeholder="e.g. Client pitch, Manchester">
    <div class="row2">
      <div><label>One-way distance (km)</label><input name="distance_km" type="number" min="1" step="1" required placeholder="320"></div>
      <div><label>Planned mode</label>
        <select name="mode">
          <option value="car_petrol">Petrol car</option>
          <option value="car_ev">Electric car</option>
          <option value="rail">Rail</option>
        </select></div>
    </div>
    <div class="check"><input type="checkbox" name="round_trip" id="rt" checked><label for="rt" style="margin:0">Round trip</label></div>
    <button class="btn go" type="submit">Get recommendation →</button>
  </form>
  <p style="margin-top:16px"><a class="back" href="/request">← All request types</a></p>
""" + PORTAL_FOOT

FLEET_FORM_TPL = PORTAL_HEAD + """
  <h1>🚚 Fleet vehicle request</h1>
  <div class="info-banner">ℹ Fleet is mostly automatic: delivery and courier routes are
    ingested from telematics and assessed continuously. Use this form only to add a
    vehicle or route manually.</div>
  <form method="post" action="/request/fleet">
""" + _FORM_IDENTITY + """
    <label>Vehicle / route name</label>
    <input name="title" required placeholder="e.g. Bristol delivery van">
    <div class="row2">
      <div><label>Daily distance (km)</label><input name="daily_km" type="number" min="1" step="1" required placeholder="110"></div>
      <div><label>Current fuel</label>
        <select name="fuel">
          <option value="diesel">Diesel</option>
          <option value="petrol">Petrol</option>
          <option value="ev">Electric</option>
        </select></div>
    </div>
    <div class="row2">
      <div><label>Candidate EV range (km)</label><input name="ev_range_km" type="number" min="1" step="1" value="250"></div>
      <div><label>Depot/overnight charging?</label>
        <select name="depot_charging">
          <option value="1">Yes</option>
          <option value="0">No</option>
        </select></div>
    </div>
    <button class="btn go" type="submit">Get recommendation →</button>
  </form>
  <p style="margin-top:16px"><a class="back" href="/request">← All request types</a></p>
""" + PORTAL_FOOT

PROCUREMENT_FORM_TPL = PORTAL_HEAD + """
  <h1>📦 Procurement request</h1>
  <p class="lead">Submit a purchased good or service. We propose the best lower-carbon
    alternative. Embodied carbon is estimated from spend (EPA factors) when you don't
    supply a figure.</p>
  <form method="post" action="/request/procurement">
""" + _FORM_IDENTITY + """
    <label>Item / service</label>
    <input name="title" required placeholder="e.g. Branded staff uniforms">
    <div class="row2">
      <div><label>Annual spend</label><input name="cost" type="number" min="0" step="1" required placeholder="9000"></div>
      <div><label>Embodied carbon (kg CO₂e, optional)</label><input name="kg_co2e" type="number" min="0" step="1" placeholder="estimate from spend"></div>
    </div>
    <button class="btn go" type="submit">Get recommendation →</button>
  </form>
  <p style="margin-top:16px"><a class="back" href="/request">← All request types</a></p>
""" + PORTAL_FOOT

_FORM_TPLS = {
    "compute": COMPUTE_FORM_TPL,
    "travel": TRAVEL_FORM_TPL,
    "fleet": FLEET_FORM_TPL,
    "procurement": PROCUREMENT_FORM_TPL,
}

EMAIL_PREVIEW_TPL = PORTAL_HEAD + """
  <h1>Your recommendation</h1>
  <p class="lead">This is the email we've sent to <b>{{ rec.email }}</b>. Review it and
    choose how to proceed.</p>
  <div class="email">
    <div class="hdr">From: carbonshift-copilot@contoso.com<br>To: {{ rec.email }}<br>Subject: {{ subject }}</div>
    <pre>{{ body }}</pre>
  </div>
  <div style="margin-bottom:14px"><span class="pill {{ rec.rec.risk }}">Risk: {{ rec.rec.risk|upper }}</span></div>
  <div class="actions">
    <a class="btn accept" href="/request/decision?id={{ rec.id }}&decision=accept">✓ Accept recommendation</a>
    <a class="btn override" href="/request/decision?id={{ rec.id }}&decision=override">⚑ Override ({{ rec.rec.override_action }})</a>
  </div>
  <p class="note">A copy of this email was saved to <code>manager_emails/{{ rec.id }}.eml</code>.
    Accepting or overriding updates the carbon-reduction team's dashboard immediately.</p>
  <p style="margin-top:14px"><a class="back" href="/request">← Submit another request</a></p>
""" + PORTAL_FOOT

OVERRIDE_FORM_TPL = PORTAL_HEAD + """
  <h1>Override recommendation</h1>
  <p class="lead">You're choosing to <b>{{ rec.rec.override_action }}</b> for
    <b>{{ rec.purpose }}</b> despite a greener option. Tell the carbon-reduction team
    why — it will be flagged on their dashboard alongside your request.</p>
  <form method="post" action="/request/decision">
    <input type="hidden" name="id" value="{{ rec.id }}">
    <input type="hidden" name="decision" value="override">
    <label>Reason</label>
    <textarea name="reason" rows="3" required placeholder="e.g. On-site equipment sign-off requires my physical presence."></textarea>
    <div class="actions">
      <button class="btn override" type="submit">Confirm override</button>
      <a class="btn ghost" href="/request/decision?id={{ rec.id }}&decision=accept">Actually, accept the recommendation</a>
    </div>
  </form>
""" + PORTAL_FOOT

DECISION_DONE_TPL = PORTAL_HEAD + """
  <h1>{{ 'Override recorded' if overridden else 'Recommendation accepted' }}</h1>
  {% if overridden %}
  <div class="over-banner">⚑ Your request <b>{{ rec.purpose }}</b> is now flagged as an
    <b>override</b> on the carbon-reduction team's dashboard. The team will still optimise
    around it to cut emissions where possible.<br><br>
    Reason on record: “{{ rec.reason }}”.</div>
  {% else %}
  <div class="ok-banner">✓ Thanks — you've accepted the recommendation for
    <b>{{ rec.purpose }}</b>. It now appears on the carbon-reduction team's dashboard with
    its ✦ AI marker and the estimated saving.</div>
  {% endif %}
  <p class="note">You can close this page. Your deadline is always honoured.</p>
  <p style="margin-top:14px"><a class="back" href="/request">← Submit another request</a></p>
""" + PORTAL_FOOT


@app.route("/request", methods=["GET"])
def request_portal():
    """Request hub: choose a domain to submit a request in."""
    return render_template_string(REQUEST_HUB_TPL)


@app.route("/request/<domain>", methods=["GET", "POST"])
def request_domain(domain):
    """Domain-specific request: show the form (GET) or run reasoning + email (POST)."""
    if domain not in _FORM_TPLS:
        return render_template_string(
            PORTAL_HEAD + "<h1>Unknown request type</h1>"
            "<p class='lead'>Pick a request type from the portal.</p>"
            "<p><a class='back' href='/request'>← All request types</a></p>" + PORTAL_FOOT
        ), 404
    if request.method == "GET":
        return render_template_string(_FORM_TPLS[domain])

    f = request.form
    payload = {
        k: f.get(k)
        for k in ("distance_km", "mode", "power_kw", "duration_hours", "due_in_hours",
                  "daily_km", "fuel", "ev_range_km", "cost", "kg_co2e")
        if f.get(k) not in (None, "")
    }
    if domain == "travel":
        payload["round_trip"] = bool(f.get("round_trip"))
    if domain == "fleet":
        payload["depot_charging"] = f.get("depot_charging", "1") == "1"
    record = requests_store.submit_request(
        domain=domain,
        requester=f.get("requester", ""),
        email=f.get("email", ""),
        title=f.get("title", ""),
        **payload,
    )
    return render_template_string(
        EMAIL_PREVIEW_TPL,
        rec=record,
        subject=requests_store.email_subject(record),
        body=requests_store.email_text(record),
    )


@app.route("/request/decision", methods=["GET", "POST"])
def request_decision():
    """Record the requester's Accept / Override choice from the emailed recommendation."""
    rid = request.values.get("id", "")
    decision = request.values.get("decision", "accept")
    record = requests_store.get_request(rid)
    if record is None:
        return render_template_string(
            PORTAL_HEAD + "<h1>Request not found</h1>"
            "<p class='lead'>That request no longer exists.</p>"
            "<p><a class='back' href='/request'>← Submit a new request</a></p>" + PORTAL_FOOT
        ), 404

    # Override via GET shows a reason form first; POST confirms it.
    if decision == "override" and request.method == "GET":
        return render_template_string(OVERRIDE_FORM_TPL, rec=record)

    reason = request.form.get("reason", "") if request.method == "POST" else ""
    updated = requests_store.decide(rid, decision, reason)
    return render_template_string(
        DECISION_DONE_TPL, rec=updated, overridden=(updated["status"] == "overridden")
    )


def main() -> None:
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
