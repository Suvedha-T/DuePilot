import json
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from models.schemas import (
    Responsibility,
    DependencyEdge,
    Plan,
    PlanDiff,
    UserPreference,
    ExtractedEvent,
    ContextResolution,
    CommunicationDraft,
    ConflictAlert,
    AgentActivityEvent,
    SubAction
)
from models.enums import WorkingPreference, Status, DependencyType, SourceChannel, ActionStatus
from database.database import (
    init_db,
    reset_db,
    get_responsibilities,
    get_responsibility_by_id,
    save_responsibility,
    get_dependencies,
    save_dependency,
    get_user_preference,
    update_user_preference,
    get_latest_plan,
    save_plan,
    get_latest_plan_diff,
    save_plan_diff,
    get_agent_events,
    get_communication_drafts,
    save_communication_draft,
    log_agent_event
)
from core.priority_engine import PriorityEngine
from core.responsibility_graph import ResponsibilityGraph
from core.conflict_detector import ConflictDetector
from core.planner import Planner
from agents.ingestion_agent import IngestionAgent
from agents.context_agent import ContextAgent
from agents.reasoning_agent import ReasoningAgent
from agents.planning_agent import PlanningAgent
from agents.replanning_agent import ReplanningAgent
from agents.execution_agent import ExecutionAgent
from core.llm_client import GeminiClient

SCENARIOS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "demo_scenarios.json")

class StateManager:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        init_db()
        self.llm = gemini_client or GeminiClient()
        self.ingestion_agent = IngestionAgent(self.llm)
        self.context_agent = ContextAgent(self.llm)
        self.reasoning_agent = ReasoningAgent(self.llm)
        self.planning_agent = PlanningAgent(self.llm)
        self.replanning_agent = ReplanningAgent(self.llm)
        self.execution_agent = ExecutionAgent(self.llm)
        self.graph_engine = ResponsibilityGraph()

    def load_scenario(self, scenario_key: str) -> None:
        """Seeds the database with a curated demo scenario."""
        reset_db()
        with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenario = data["scenarios"].get(scenario_key)
        if not scenario:
            raise ValueError(f"Unknown scenario key: {scenario_key}")

        now = datetime.now()

        # Seed responsibilities
        for r_data in scenario.get("responsibilities", []):
            days = r_data.get("days_to_deadline", 3)
            deadline = now + timedelta(days=days)
            
            subactions = [
                SubAction(
                    id=a["id"],
                    responsibility_id=r_data["id"],
                    title=a["title"],
                    estimated_minutes=a["estimated_minutes"],
                    status=Status(a.get("status", "pending")),
                    order_idx=idx,
                    is_blocked=a.get("is_blocked", False),
                    blocker_reason=a.get("blocker_reason")
                )
                for idx, a in enumerate(r_data.get("subactions", []))
            ]

            resp = Responsibility(
                id=r_data["id"],
                title=r_data["title"],
                category=r_data.get("category", "Academic"),
                description=r_data.get("description", ""),
                deadline=deadline,
                deadline_str=r_data.get("deadline_str"),
                estimated_hours=r_data.get("estimated_hours", 1.0),
                consequence_score=r_data.get("consequence_score", 50.0),
                importance_score=r_data.get("importance_score", 50.0),
                difficulty_level=r_data.get("difficulty_level", 3),
                status=Status(r_data.get("status", "pending")),
                is_blocked=r_data.get("is_blocked", False),
                blocker_reason=r_data.get("blocker_reason"),
                subactions=subactions,
                created_at=now,
                updated_at=now
            )
            save_responsibility(resp)

        # Seed dependencies
        for d_data in scenario.get("dependencies", []):
            edge = DependencyEdge(
                id=d_data["id"],
                from_node=d_data["from_node"],
                to_node=d_data["to_node"],
                dependency_type=DependencyType(d_data.get("dependency_type", "depends_on")),
                description=d_data.get("description", "")
            )
            save_dependency(edge)

        # Seed initial blocker draft if present in scenario
        if "blocker_draft" in scenario:
            bd = scenario["blocker_draft"]
            draft = CommunicationDraft(
                id="draft_scen_blocker",
                recipient=bd["recipient"],
                channel=SourceChannel(bd.get("channel", "WhatsApp")),
                subject=bd.get("subject"),
                body=bd["body"],
                status=ActionStatus.PROPOSED,
                reason=bd["reason"],
                related_responsibility_id=scenario["responsibilities"][0]["id"],
                created_at=now
            )
            save_communication_draft(draft)

        # Build initial priorities and plan
        user_pref = get_user_preference()
        resps = get_responsibilities()
        ranked = self.reasoning_agent.evaluate_and_rank(resps, user_pref)
        for r in ranked:
            save_responsibility(r)

        self.planning_agent.plan(ranked, user_pref)

        log_agent_event(
            AgentActivityEvent(
                id=f"evt_init_{datetime.now().strftime('%H%M%S')}",
                agent_name="DuePilot Orchestrator",
                activity_type="scenario_loaded",
                message=f"Initialized '{scenario['name']}' environment with {len(resps)} responsibilities.",
                status="success",
                details={"scenario": scenario["name"]}
            )
        )

    def process_new_information(self, raw_text: str, source_channel: str = "Direct Input") -> Tuple[ExtractedEvent, ContextResolution, Plan, PlanDiff]:
        """Core agentic loop: Observe -> Understand -> Update World State -> Reason -> Prioritize -> Plan -> Act -> Replan"""
        # 1. INGESTION AGENT: Observe & Understand
        extracted = self.ingestion_agent.process(raw_text, source_channel)

        # 2. CONTEXT AGENT: Link to World State
        existing_resps = get_responsibilities()
        resolution = self.context_agent.resolve(extracted, existing_resps)

        now = datetime.now()
        previous_plan = get_latest_plan()

        # 3. UPDATE WORLD STATE in SQLite
        if resolution.action_type == "change_deadline" and resolution.matched_responsibility_id:
            target = get_responsibility_by_id(resolution.matched_responsibility_id)
            if target:
                target.deadline_str = resolution.changes.get("new_deadline", "Tomorrow, 10:00 AM")
                target.deadline = now + timedelta(hours=16)  # Set to tomorrow morning
                target.updated_at = now
                save_responsibility(target)
        elif resolution.action_type == "add_blocker" and resolution.matched_responsibility_id:
            target = get_responsibility_by_id(resolution.matched_responsibility_id)
            if target:
                target.is_blocked = True
                target.blocker_reason = resolution.changes.get("blocker_reason", "External dependency pending")
                target.updated_at = now
                save_responsibility(target)
        elif resolution.action_type == "create_new":
            new_r = Responsibility(
                id=f"resp_{now.strftime('%Y%m%d%H%M%S')}",
                title=extracted.responsibility_title,
                category="Academic",
                description=extracted.action_summary,
                deadline=now + timedelta(days=2),
                deadline_str=extracted.deadline or "In 2 days",
                estimated_hours=2.0,
                consequence_score=80.0,
                importance_score=80.0,
                difficulty_level=3,
                status=Status.PENDING,
                created_at=now,
                updated_at=now
            )
            save_responsibility(new_r)

        # 4. REASONING AGENT: Recalculate priorities
        user_pref = get_user_preference()
        updated_resps = get_responsibilities()
        ranked = self.reasoning_agent.evaluate_and_rank(updated_resps, user_pref)
        for r in ranked:
            save_responsibility(r)

        # 5. REPLANNING AGENT: Compare BEFORE -> EVENT -> AFTER
        new_plan, plan_diff = self.replanning_agent.replan(
            trigger_event=raw_text,
            current_plan=previous_plan,
            responsibilities=ranked,
            user_pref=user_pref
        )

        return extracted, resolution, new_plan, plan_diff

    def simulate_deadline_shock(self) -> Tuple[Plan, PlanDiff]:
        """Executes the signature Deadline Shock demo scenario seamlessly."""
        shock_text = "Placement aptitude test has been moved from Friday to tomorrow at 10 AM."
        _, _, new_plan, plan_diff = self.process_new_information(shock_text, source_channel="College Portal")
        return new_plan, plan_diff

    def get_dashboard_summary(self) -> Dict[str, Any]:
        user_pref = get_user_preference()
        resps = get_responsibilities()
        deps = get_dependencies()
        plan = get_latest_plan()
        diff = get_latest_plan_diff()
        drafts = get_communication_drafts()
        events = get_agent_events(limit=15)
        conflicts = ConflictDetector.detect_conflicts(resps, user_pref)

        # Build graph
        self.graph_engine.build(resps, deps)
        graph_stats = self.graph_engine.get_stats()

        active_count = sum(1 for r in resps if r.status != Status.COMPLETED)
        blocked_count = sum(1 for r in resps if r.is_blocked)
        critical_count = sum(1 for r in resps if (r.priority_breakdown and r.priority_breakdown.total_score >= 80))

        # Hero next action
        hero_task = None
        for r in resps:
            if not r.is_blocked and r.status != Status.COMPLETED:
                hero_task = r
                break
        if not hero_task and resps:
            hero_task = resps[0]

        return {
            "user_pref": user_pref,
            "responsibilities": resps,
            "dependencies": deps,
            "latest_plan": plan,
            "latest_diff": diff,
            "drafts": drafts,
            "events": events,
            "conflicts": conflicts,
            "graph_engine": self.graph_engine,
            "graph_stats": graph_stats,
            "active_count": active_count,
            "blocked_count": blocked_count,
            "critical_count": critical_count,
            "hero_task": hero_task
        }
