import json
import uuid
from typing import List, Optional
import google.adk as adk
from models.schemas import ExtractedEvent, ContextResolution, Responsibility, AgentActivityEvent
from prompts.context_prompts import CONTEXT_PROMPT
from core.llm_client import GeminiClient
from database.database import log_agent_event

class ContextAgent:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.llm = gemini_client or GeminiClient()
        self.adk_agent = adk.Agent(
            name="ContextAgent",
            instruction=(
                "Resolve relationships between incoming events and existing commitments. "
                "Detect deadline changes, blockers, and dependencies accurately."
            )
        )

    def resolve(
        self,
        event: ExtractedEvent,
        existing_responsibilities: List[Responsibility]
    ) -> ContextResolution:
        resolution: Optional[ContextResolution] = None

        if self.llm.is_available() and existing_responsibilities:
            current_json = json.dumps([
                {
                    "id": r.id,
                    "title": r.title,
                    "category": r.category,
                    "deadline": r.deadline_str,
                    "status": r.status.value,
                    "is_blocked": r.is_blocked
                }
                for r in existing_responsibilities
            ], indent=2)
            event_json = event.model_dump_json(indent=2)
            prompt = CONTEXT_PROMPT.format(
                current_responsibilities_json=current_json,
                incoming_event_json=event_json
            )
            model_obj, err = self.llm.generate_json(prompt, ContextResolution)
            if model_obj and isinstance(model_obj, ContextResolution):
                resolution = model_obj

        if not resolution:
            resolution = self._heuristic_resolve(event, existing_responsibilities)

        # Log agent activity
        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="ContextAgent",
            activity_type="context_resolution",
            message=f"Context linked: {resolution.action_type.replace('_', ' ').title()} -> '{resolution.matched_responsibility_title or event.responsibility_title}'",
            status="info",
            details={
                "action_type": resolution.action_type,
                "matched_id": resolution.matched_responsibility_id,
                "reasoning": resolution.reasoning
            }
        )
        log_agent_event(act_event)

        return resolution

    def _heuristic_resolve(
        self,
        event: ExtractedEvent,
        existing_responsibilities: List[Responsibility]
    ) -> ContextResolution:
        event_title_lower = event.responsibility_title.lower()
        req_text = " ".join(event.requirements).lower()
        combined = f"{event_title_lower} {req_text}"

        matched_r: Optional[Responsibility] = None

        for r in existing_responsibilities:
            r_title_lower = r.title.lower()
            # Token overlap check
            words_r = set(w for w in r_title_lower.split() if len(w) > 2)
            words_event = set(w for w in combined.split() if len(w) > 2)
            common = words_r.intersection(words_event)
            
            # Specific domain matching
            if ("placement" in r_title_lower and "placement" in combined) or \
               ("aptitude" in r_title_lower and "aptitude" in combined) or \
               ("ml" in r_title_lower and ("ml" in combined or "machine learning" in combined)) or \
               ("daa" in r_title_lower and "daa" in combined) or \
               ("internship" in r_title_lower and "internship" in combined):
                matched_r = r
                break
            elif len(common) >= 2:
                matched_r = r
                break

        # Check for deadline change
        is_deadline_shock = any(u in combined for u in ["moved", "rescheduled", "postponed", "tomorrow at 10 am"])
        if matched_r and is_deadline_shock and event.deadline:
            return ContextResolution(
                action_type="change_deadline",
                matched_responsibility_id=matched_r.id,
                matched_responsibility_title=matched_r.title,
                reasoning=f"Detected deadline shift for existing commitment '{matched_r.title}'.",
                changes={
                    "new_deadline": event.deadline,
                    "updated_fields": ["deadline", "deadline_str"]
                }
            )

        # Check for blocker
        if matched_r and ("blocked" in combined or "waiting for" in combined or "missing" in combined):
            return ContextResolution(
                action_type="add_blocker",
                matched_responsibility_id=matched_r.id,
                matched_responsibility_title=matched_r.title,
                reasoning=f"Identified external blocker preventing progress on '{matched_r.title}'.",
                changes={
                    "blocker_reason": event.requirements[0] if event.requirements else "Waiting on external dependency",
                    "updated_fields": ["is_blocked", "blocker_reason"]
                }
            )

        if matched_r:
            return ContextResolution(
                action_type="update_existing",
                matched_responsibility_id=matched_r.id,
                matched_responsibility_title=matched_r.title,
                reasoning=f"Updated details for active responsibility '{matched_r.title}'.",
                changes={"updated_fields": ["description"]}
            )

        return ContextResolution(
            action_type="create_new",
            matched_responsibility_id=None,
            matched_responsibility_title=None,
            reasoning="No existing match found. Created new responsibility in graph.",
            changes={}
        )
