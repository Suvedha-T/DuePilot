import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.state_manager import StateManager
from database.database import (
    init_db, get_user_preference, update_user_preference,
    get_responsibilities, get_latest_plan, get_latest_plan_diff,
    get_agent_events, get_communication_drafts
)
from models.enums import WorkingPreference, ActionStatus, SourceChannel, Status

st.set_page_config(page_title="DuePilot", page_icon="✈️", layout="wide", initial_sidebar_state="expanded")

# ---------- Styling ----------
st.markdown("""
<style>
:root { --bg:#07111f; --panel:#0d1b2a; --panel2:#101f31; --text:#e8f0f7; --muted:#91a4b7; --accent:#48c6ff; --purple:#8b7cff; --danger:#ff647c; --success:#35d49a; --warning:#ffb454; }
.stApp { background: radial-gradient(circle at 15% 0%, rgba(72,198,255,.10), transparent 30%), radial-gradient(circle at 90% 10%, rgba(139,124,255,.10), transparent 28%), var(--bg); color:var(--text); }
[data-testid="stSidebar"] { background:#081522; border-right:1px solid rgba(255,255,255,.07); }
.block-container { max-width: 1380px; padding-top: 1.2rem; }
.dp-brand { font-size:1.55rem; font-weight:800; letter-spacing:-.04em; }
.dp-brand span { color:var(--accent); }
.dp-tag { color:var(--muted); font-size:.84rem; margin-top:-6px; }
.hero { padding:28px 30px; border:1px solid rgba(72,198,255,.20); border-radius:24px; background:linear-gradient(135deg,rgba(21,45,65,.95),rgba(12,25,40,.92)); box-shadow:0 18px 50px rgba(0,0,0,.22); }
.eyebrow { color:var(--accent); font-size:.75rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; }
.hero-title { font-size:2.35rem; font-weight:850; letter-spacing:-.055em; margin:4px 0 4px; }
.hero-sub { color:var(--muted); max-width:760px; }
.metric { background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.065); border-radius:17px; padding:16px; }
.metric .n { font-size:1.65rem; font-weight:800; }
.metric .l { color:var(--muted); font-size:.78rem; }
.card { background:rgba(13,27,42,.88); border:1px solid rgba(255,255,255,.07); border-radius:18px; padding:19px; margin-bottom:12px; }
.card-title { font-weight:800; font-size:1rem; }
.muted { color:var(--muted); }
.pill { display:inline-block; border-radius:999px; padding:4px 9px; font-size:.72rem; font-weight:700; background:rgba(72,198,255,.12); color:#9edfff; }
.pill-danger { background:rgba(255,100,124,.13); color:#ff9aaa; }
.pill-success { background:rgba(53,212,154,.12); color:#79e9bf; }
.pill-warning { background:rgba(255,180,84,.13); color:#ffd08e; }
.score { font-size:2rem; font-weight:850; line-height:1; }
.reason { color:#b7c6d5; font-size:.82rem; line-height:1.45; }
.event { border-left:3px solid var(--accent); padding:9px 12px; margin:8px 0; background:rgba(255,255,255,.025); border-radius:0 10px 10px 0; }
.small { font-size:.78rem; }
hr { border-color:rgba(255,255,255,.08); }
div[data-testid="stMetricValue"] { color:var(--text); }
button[kind="primary"] { border-radius:12px; }
</style>
""", unsafe_allow_html=True)

init_db()

@st.cache_resource

def get_manager():
    return StateManager()

manager = get_manager()

# ---------- Helpers ----------
def fmt_deadline(r):
    if r.deadline_str:
        return r.deadline_str
    if r.deadline:
        return r.deadline.strftime("%d %b, %I:%M %p")
    return "No deadline"

def score(r):
    return r.priority_breakdown.total_score if r.priority_breakdown else 0

def badge(r):
    if r.is_blocked:
        return '<span class="pill pill-danger">BLOCKED</span>'
    s = score(r)
    if s >= 80:
        return '<span class="pill pill-warning">CRITICAL</span>'
    if s >= 60:
        return '<span class="pill">HIGH</span>'
    return '<span class="pill pill-success">ON TRACK</span>'

def render_responsibility(r, expanded=False):
    st.markdown(f"""
    <div class="card">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
        <div>
          <div class="small muted">{r.category.upper()} · {fmt_deadline(r)}</div>
          <div class="card-title" style="font-size:1.08rem;margin-top:4px">{r.title}</div>
          <div class="small muted" style="margin-top:5px">{r.description}</div>
        </div>
        <div style="text-align:right">{badge(r)}<div class="score" style="font-size:1.45rem;margin-top:7px">{score(r):.0f}</div><div class="small muted">priority</div></div>
      </div>
      <div style="display:flex;gap:18px;margin-top:14px" class="small muted">
        <span>⏱ {r.estimated_hours:g}h</span><span>⚡ consequence {r.consequence_score:.0f}</span><span>🎯 difficulty {r.difficulty_level}/5</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
    if expanded:
        with st.expander("Why this priority?", expanded=True):
            b = r.priority_breakdown
            if b:
                cols = st.columns(4)
                vals = [("Deadline", b.deadline_urgency), ("Consequence", b.consequence), ("Dependency", b.dependency_impact), ("Effort risk", b.effort_risk), ("Preference", b.personal_preference), ("Focus fit", b.focus_fit), ("History", b.historical_behavior)]
                for i,(label,val) in enumerate(vals):
                    cols[i % 4].metric(label, f"+{val:.1f}")
                st.info(b.explanation_summary)
            if r.is_blocked:
                st.warning(f"Blocked: {r.blocker_reason}")

def plan_timeline(plan):
    if not plan or not plan.schedule_blocks:
        st.info("No schedule blocks yet.")
        return
    for b in plan.schedule_blocks:
        icon = "◻️" if b.block_type == "task" else "·"
        color = "#48c6ff" if b.block_type == "task" else "#64748b"
        st.markdown(f"""
        <div style="display:flex;gap:15px;align-items:center;padding:11px 0;border-bottom:1px solid rgba(255,255,255,.06)">
          <div style="width:90px;color:#91a4b7;font-size:.8rem">{b.start_time}<br>{b.end_time}</div>
          <div style="width:10px;height:10px;border-radius:50%;background:{color};box-shadow:0 0 12px {color}"></div>
          <div><b>{icon} {b.title}</b><div class="small muted">{b.duration_minutes} min · {b.notes}</div></div>
        </div>""", unsafe_allow_html=True)

def reload():
    st.rerun()

# ---------- Sidebar ----------
st.sidebar.markdown('<div class="dp-brand">✈️ Due<span>Pilot</span></div><div class="dp-tag">Navigate what matters next.</div>', unsafe_allow_html=True)
st.sidebar.markdown("---")
mode = st.sidebar.radio("Mode", ["Command Center", "Live Input", "Responsibility Map", "Today's Plan", "Why This?", "Agent Activity", "Insights"], index=0)
st.sidebar.markdown("### Demo cockpit")
scenario_names = {"normal_day":"Normal Day", "deadline_shock":"Deadline Shock", "dependency_blocked":"Dependency Blocked", "overloaded_week":"Overloaded Week"}
scenario = st.sidebar.selectbox("Scenario", list(scenario_names.keys()), index=1, format_func=lambda x: scenario_names[x])
if st.sidebar.button("↻ Load / Reset Scenario", use_container_width=True):
    manager.load_scenario(scenario)
    st.session_state["last_scenario"] = scenario
    st.session_state["just_loaded"] = True
    reload()

pref = get_user_preference()
new_pref = st.sidebar.selectbox("Working style", [p.value for p in WorkingPreference], index=[p.value for p in WorkingPreference].index(pref.preference.value))
if new_pref != pref.preference.value:
    pref.preference = WorkingPreference(new_pref)
    update_user_preference(pref)
    # Re-score and re-plan using current state
    resps = get_responsibilities()
    ranked = manager.reasoning_agent.evaluate_and_rank(resps, pref)
    for r in ranked:
        from database.database import save_responsibility
        save_responsibility(r)
    manager.planning_agent.plan(ranked, pref)
    reload()

st.sidebar.caption("Demo Mode is deterministic: it remains usable even if Gemini is unavailable.")

# ---------- Load default scenario on first run ----------
if not get_responsibilities():
    manager.load_scenario("deadline_shock")

summary = manager.get_dashboard_summary()
resps = sorted(summary["responsibilities"], key=score, reverse=True)
hero = next((r for r in resps if not r.is_blocked and r.status != Status.COMPLETED), resps[0] if resps else None)

# ---------- Header ----------
st.markdown(f"<div class='dp-brand'>✈️ Due<span>Pilot</span></div><div class='dp-tag'>Responsibility intelligence · {datetime.now().strftime('%A, %d %B')}</div>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ---------- Command Center ----------
if mode == "Command Center":
    if hero:
        st.markdown(f"""
        <div class="hero">
          <div class="eyebrow">NEXT BEST ACTION</div>
          <div class="hero-title">{hero.title}</div>
          <div class="hero-sub">{hero.description}</div>
          <div style="display:flex;gap:28px;margin-top:18px;flex-wrap:wrap">
            <div><div class="small muted">DEADLINE</div><b>{fmt_deadline(hero)}</b></div>
            <div><div class="small muted">EFFORT</div><b>{hero.estimated_hours:g} hours</b></div>
            <div><div class="small muted">PRIORITY</div><b style="color:#48c6ff">{score(hero):.0f}/100</b></div>
          </div>
          <div style="margin-top:16px;padding:12px 14px;background:rgba(255,255,255,.04);border-radius:12px"><b>Why now?</b><br><span class="reason">{hero.priority_breakdown.explanation_summary if hero.priority_breakdown else 'Priority is being calculated.'}</span></div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    m = st.columns(4)
    m[0].metric("Active", summary["active_count"])
    m[1].metric("Critical", summary["critical_count"])
    m[2].metric("Blocked", summary["blocked_count"])
    m[3].metric("Graph nodes", summary["graph_stats"]["total_nodes"])

    if summary["conflicts"]:
        st.warning(" · ".join(c.message for c in summary["conflicts"][:2]))

    # Flagship judge interaction: deterministic Deadline Shock
    if scenario == "deadline_shock":
        st.markdown("### ⚡ Signature demo")
        st.caption("Show how a single new event changes the entire route.")
        if st.button("Simulate Deadline Shock", type="primary", use_container_width=True):
            manager.simulate_deadline_shock()
            st.session_state["shock_ran"] = True
            reload()
        if st.session_state.get("shock_ran") and summary.get("latest_diff"):
            diff = summary["latest_diff"]
            st.success("PLAN CHANGED — DuePilot detected a schedule disruption and recalculated the optimal route.")
            c1,c2 = st.columns(2)
            with c1:
                st.markdown("**EVENT**")
                st.info(diff.trigger_event)
            with c2:
                st.markdown("**REASON**")
                st.info(diff.reason)
            for change in diff.timeline_changes[:5]:
                st.write(change)

    left,right = st.columns([1.35,1])
    with left:
        st.markdown("### Priority queue")
        for r in resps[:6]:
            render_responsibility(r)
    with right:
        st.markdown("### Today's route")
        plan_timeline(summary["latest_plan"])
        if st.button("⚡ Recalculate route", type="primary", use_container_width=True):
            plan = manager.replanning_agent.replan("Manual route recalculation", summary["latest_plan"], resps, pref)[0]
            st.success(f"Route recalculated. Top action: {plan.ranked_responsibilities[0]['title'] if plan.ranked_responsibilities else 'None'}")
            reload()

    st.markdown("### Agent pulse")
    events = summary["events"][:6]
    cols = st.columns(min(3, max(1,len(events))))
    for i,e in enumerate(events):
        with cols[i % len(cols)]:
            st.markdown(f"<div class='event'><b>{e.agent_name}</b><br><span class='small'>{e.message}</span></div>", unsafe_allow_html=True)

# ---------- Live Input ----------
elif mode == "Live Input":
    st.markdown("## Add new information")
    st.caption("Paste an email, classroom announcement, portal update or message. DuePilot will turn it into responsibility state.")
    source = st.selectbox("Source", ["Direct Input", "Gmail", "WhatsApp", "Google Classroom", "College Portal"])
    raw = st.text_area("Incoming information", height=180, placeholder="Example: Placement aptitude test has been moved from Friday to tomorrow at 10 AM.")
    if st.button("Analyze with DuePilot", type="primary"):
        if not raw.strip():
            st.warning("Add some information first.")
        else:
            with st.status("DuePilot is reasoning…", expanded=True) as status:
                st.write("1 · Ingestion Agent — extracting actionable information")
                extracted, resolution, plan, diff = manager.process_new_information(raw, source)
                st.write("2 · Context Agent — connecting it to existing responsibilities")
                st.write("3 · Reasoning Agent — recalculating priority")
                st.write("4 · Replanning Agent — generating a new route")
                status.update(label="Plan updated", state="complete")
            st.markdown("### What changed")
            a,b = st.columns(2)
            with a:
                st.markdown("#### Interpreted input")
                st.json(extracted.model_dump(mode="json"))
            with b:
                st.markdown("#### Context decision")
                st.info(f"**{resolution.action_type.replace('_',' ').title()}** — {resolution.reasoning}")
            if diff:
                st.markdown("### Before → Event → After")
                st.success(diff.reason)
                for change in diff.timeline_changes:
                    st.write(change)
                if diff.conflicts_detected:
                    st.warning(" · ".join(diff.conflicts_detected))
            st.markdown("### New route")
            plan_timeline(plan)

# ---------- Responsibility Map ----------
elif mode == "Responsibility Map":
    st.markdown("## Responsibility Map")
    st.caption("DuePilot models responsibilities as a connected system—not a flat task list.")
    fig = summary["graph_engine"].to_plotly_figure()
    fig.update_layout(height=650, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    a,b,c,d = st.columns(4)
    stats = summary["graph_stats"]
    a.metric("Responsibilities", stats["responsibilities"])
    b.metric("Actions", stats["actions"])
    c.metric("Dependencies", stats["dependencies"])
    d.metric("Blocked", stats["blocked"])
    st.markdown("### Selected responsibilities")
    for r in resps:
        render_responsibility(r)

# ---------- Plan ----------
elif mode == "Today's Plan":
    st.markdown("## Today's Plan")
    plan = summary["latest_plan"]
    if plan:
        c1,c2,c3 = st.columns(3)
        c1.metric("Planned workload", f"{plan.total_workload_hours:.1f}h")
        c2.metric("Available", f"{plan.available_hours:.1f}h")
        c3.metric("Status", "OVERLOADED" if plan.is_overloaded else "BALANCED")
        if plan.is_overloaded:
            st.warning("Your workload exceeds today's available time. DuePilot is protecting buffer and prioritizing the highest-impact work.")
        plan_timeline(plan)
    st.markdown("### Ranked responsibilities")
    for r in resps:
        render_responsibility(r)

# ---------- Why ----------
elif mode == "Why This?":
    st.markdown("## Why this?")
    st.caption("Explainable prioritization: the agent recommends, the student decides.")
    for r in resps[:8]:
        b = r.priority_breakdown
        if not b: continue
        with st.expander(f"#{b.rank}  {r.title} — {b.total_score:.0f}/100", expanded=(b.rank==1)):
            cols=st.columns(4)
            for i,(label,val) in enumerate([("Deadline",b.deadline_urgency),("Consequence",b.consequence),("Dependency",b.dependency_impact),("Effort risk",b.effort_risk),("Preference",b.personal_preference),("Focus fit",b.focus_fit),("History",b.historical_behavior)]):
                cols[i%4].metric(label,f"+{val:.1f}")
            st.markdown(f"**Reason:** {b.explanation_summary}")

# ---------- Agent Activity ----------
elif mode == "Agent Activity":
    st.markdown("## Agent Activity")
    st.caption("The system's reasoning loop is observable and auditable.")
    for e in summary["events"]:
        icon = "✓" if e.status == "success" else ("⚠" if e.status == "warning" else ("⏳" if e.status == "action_needed" else "•"))
        st.markdown(f"<div class='event'><b>{icon} {e.agent_name}</b> <span class='small muted'>{e.timestamp.strftime('%H:%M:%S')}</span><br>{e.message}</div>", unsafe_allow_html=True)
    st.markdown("### Current communication actions")
    drafts = summary["drafts"]
    if not drafts:
        st.info("No approval-required actions yet.")
    for d in drafts:
        st.markdown(f"<div class='card'><b>{d.recipient}</b> · {d.channel.value}<br><span class='small muted'>{d.reason}</span><hr>{d.body}</div>", unsafe_allow_html=True)
        if d.status == ActionStatus.PROPOSED:
            c1,c2 = st.columns(2)
            if c1.button("Approve", key=f"approve_{d.id}"):
                manager.execution_agent.approve_action(d.id, d.related_responsibility_id)
                st.success("Approved. Blocker marked resolved.")
                reload()
            if c2.button("Reject", key=f"reject_{d.id}"):
                manager.execution_agent.reject_action(d.id)
                reload()

# ---------- Insights ----------
elif mode == "Insights":
    st.markdown("## Insights")
    categories = {}
    for r in resps:
        categories[r.category] = categories.get(r.category,0)+r.estimated_hours
    fig = go.Figure(go.Bar(x=list(categories.keys()), y=list(categories.values()), text=[f"{v:.1f}h" for v in categories.values()], textposition="outside"))
    fig.update_layout(title="Workload by responsibility type", yaxis_title="Hours", height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
    overdue = sum(1 for r in resps if r.deadline and r.deadline < datetime.now() and r.status != Status.COMPLETED)
    blocked = sum(1 for r in resps if r.is_blocked)
    total = sum(r.estimated_hours for r in resps if r.status != Status.COMPLETED)
    c1,c2,c3 = st.columns(3)
    c1.metric("Total active effort", f"{total:.1f}h")
    c2.metric("Blocked responsibilities", blocked)
    c3.metric("Past deadline", overdue)

st.markdown("<br><hr><div class='small muted' style='text-align:center'>DuePilot · Agentic responsibility intelligence · Human approval for consequential actions</div>", unsafe_allow_html=True)
