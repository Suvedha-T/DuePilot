import uuid
from typing import List, Optional
import google.adk as adk
from models.schemas import Responsibility, Plan, UserPreference, AgentActivityEvent
from core.planner import Planner
from core.conflict_detector import ConflictDetector
from core.llm_client import GeminiClient
from database.database import log_agent_event, save_plan

class PlanningAgent:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.llm = gemini_client or GeminiClient()
        self.adk_agent = adk.Agent(
            name="PlanningAgent",
            instruction=(
                "Synthesize a balanced, realistic schedule that protects buffer time and "
                "aligns with student cognitive capacity and working preferences."
            )
        )

    def plan(
        self,
        ranked_responsibilities: List[Responsibility],
        user_pref: UserPreference
    ) -> Plan:
        # 1. Detect conflicts
        conflicts = ConflictDetector.detect_conflicts(ranked_responsibilities, user_pref)

        # 2. Build schedule
        new_plan = Planner.generate_plan(ranked_responsibilities, user_pref)

        # 3. Save plan to database
        save_plan(new_plan)

        # 4. Log agent activity
        status = "warning" if new_plan.is_overloaded else "success"
        msg = f"Generated daily plan ({len(new_plan.schedule_blocks)} blocks scheduled). "
        if new_plan.is_overloaded:
            msg += f"⚠️ Overloaded: {new_plan.total_workload_hours}h active workload exceeds {new_plan.available_hours}h capacity."
        else:
            msg += f"Reserved {new_plan.buffer_hours}h protected buffer."

        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="PlanningAgent",
            activity_type="schedule_planning",
            message=msg,
            status=status,
            details={
                "scheduled_blocks": len(new_plan.schedule_blocks),
                "is_overloaded": new_plan.is_overloaded,
                "total_workload": new_plan.total_workload_hours,
                "conflicts_count": len(conflicts)
            }
        )
        log_agent_event(act_event)

        return new_plan
