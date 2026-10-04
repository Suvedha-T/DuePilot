import uuid
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import google.adk as adk
from models.schemas import Responsibility, Plan, PlanDiff, UserPreference, AgentActivityEvent
from core.planner import Planner
from core.conflict_detector import ConflictDetector
from core.priority_engine import PriorityEngine
from core.llm_client import GeminiClient
from database.database import log_agent_event, save_plan, save_plan_diff

class ReplanningAgent:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.llm = gemini_client or GeminiClient()
        self.adk_agent = adk.Agent(
            name="ReplanningAgent",
            instruction=(
                "Evaluate schedule disruptions, calculate downstream impact, regenerate "
                "the optimal plan, and provide complete transparent BEFORE -> EVENT -> AFTER explanations."
            )
        )

    def replan(
        self,
        trigger_event: str,
        current_plan: Optional[Plan],
        responsibilities: List[Responsibility],
        user_pref: UserPreference
    ) -> Tuple[Plan, PlanDiff]:
        from typing import Tuple

        # 1. Recalculate priorities
        re_ranked = PriorityEngine.rank_responsibilities(responsibilities, user_pref)

        # 2. Detect conflicts
        conflicts = ConflictDetector.detect_conflicts(re_ranked, user_pref)
        conflict_msgs = [c.message for c in conflicts]

        # 3. Generate new revised plan
        new_plan = Planner.generate_plan(re_ranked, user_pref)
        save_plan(new_plan)

        # 4. Compare BEFORE and AFTER
        old_order_map: Dict[str, int] = {}
        old_plan_id = None
        if current_plan:
            old_plan_id = current_plan.id
            for item in current_plan.ranked_responsibilities:
                old_order_map[item.get("title", "")] = item.get("rank", 99)

        rank_changes: List[Dict[str, Any]] = []
        timeline_changes: List[str] = []

        for item in new_plan.ranked_responsibilities:
            title = item.get("title", "")
            new_rank = item.get("rank", 99)
            old_rank = old_order_map.get(title, None)

            rank_changes.append({
                "title": title,
                "old_rank": old_rank if old_rank is not None else "-",
                "new_rank": new_rank,
                "shift": (old_rank - new_rank) if old_rank is not None else 0,
                "priority_score": item.get("priority_score", 0),
                "is_blocked": item.get("is_blocked", False)
            })

            if old_rank is not None and old_rank != new_rank:
                if new_rank < old_rank:
                    timeline_changes.append(f"🔺 '{title}' promoted from #{old_rank} to #{new_rank}")
                else:
                    timeline_changes.append(f"🔻 '{title}' shifted from #{old_rank} to #{new_rank}")

        # Explain why plan changed
        reason = f"Schedule disruption: {trigger_event}. Recalculated optimal path."
        if timeline_changes:
            reason = f"Event '{trigger_event}' altered urgency windows: {timeline_changes[0]}."

        plan_diff = PlanDiff(
            previous_plan_id=old_plan_id,
            new_plan_id=new_plan.id,
            trigger_event=trigger_event,
            reason=reason,
            rank_changes=rank_changes,
            timeline_changes=timeline_changes,
            conflicts_detected=conflict_msgs,
            created_at=datetime.now()
        )
        save_plan_diff(plan_diff)

        # Log agent activity
        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="ReplanningAgent",
            activity_type="dynamic_replanning",
            message=f"Plan revised: {trigger_event} -> Top task is now '{new_plan.ranked_responsibilities[0]['title'] if new_plan.ranked_responsibilities else 'N/A'}'",
            status="warning" if conflicts else "success",
            details={
                "trigger": trigger_event,
                "shifts_count": len(timeline_changes),
                "conflicts": conflict_msgs
            }
        )
        log_agent_event(act_event)

        return new_plan, plan_diff
