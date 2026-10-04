import uuid
from typing import List, Optional, Dict
import google.adk as adk
from models.schemas import Responsibility, UserPreference, PriorityBreakdown, AgentActivityEvent
from core.priority_engine import PriorityEngine
from core.llm_client import GeminiClient
from database.database import log_agent_event

class ReasoningAgent:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.llm = gemini_client or GeminiClient()
        self.adk_agent = adk.Agent(
            name="ReasoningAgent",
            instruction=(
                "Evaluate responsibilities for deadline urgency, consequence impact, "
                "effort risk, and focus readiness. Produce transparent explainable factors."
            )
        )

    def evaluate_and_rank(
        self,
        responsibilities: List[Responsibility],
        user_pref: UserPreference,
        dependency_map: Optional[Dict[str, List[str]]] = None
    ) -> List[Responsibility]:
        ranked = PriorityEngine.rank_responsibilities(
            responsibilities=responsibilities,
            user_pref=user_pref,
            dependency_map=dependency_map
        )

        # Log agent activity
        top_task = ranked[0].title if ranked else "None"
        top_score = ranked[0].priority_breakdown.total_score if (ranked and ranked[0].priority_breakdown) else 0
        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="ReasoningAgent",
            activity_type="priority_reasoning",
            message=f"Evaluated {len(ranked)} commitments. Top recommendation: '{top_task}' (Score: {top_score:.0f}/100)",
            status="success",
            details={
                "evaluated_count": len(ranked),
                "top_recommendation": top_task,
                "top_score": top_score
            }
        )
        log_agent_event(act_event)

        return ranked
