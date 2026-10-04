import uuid
from typing import Optional
from datetime import datetime
import google.adk as adk
from models.schemas import CommunicationDraft, AgentActivityEvent
from models.enums import ActionStatus, SourceChannel, Status
from prompts.action_prompts import ACTION_PROMPT
from core.llm_client import GeminiClient
from database.database import (
    save_communication_draft,
    update_draft_status,
    get_responsibility_by_id,
    save_responsibility,
    log_agent_event
)

class ExecutionAgent:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.llm = gemini_client or GeminiClient()
        self.adk_agent = adk.Agent(
            name="ExecutionAgent",
            instruction=(
                "Implement controlled actions. Consequential actions require explicit human approval. "
                "Draft clear, low-friction communications to unblock student commitments."
            )
        )

    def prepare_blocker_resolution_draft(
        self,
        responsibility_id: str,
        responsibility_title: str,
        blocker_reason: str,
        recipient: str = "Teammate / Collaborator",
        channel: SourceChannel = SourceChannel.WHATSAPP
    ) -> CommunicationDraft:
        draft_content: Optional[CommunicationDraft] = None

        if self.llm.is_available():
            prompt = ACTION_PROMPT.format(
                responsibility_title=responsibility_title,
                blocker_reason=blocker_reason,
                recipient=recipient,
                channel=channel.value
            )
            model_obj, err = self.llm.generate_json(prompt, CommunicationDraft)
            if model_obj and isinstance(model_obj, CommunicationDraft):
                draft_content = model_obj

        if not draft_content:
            body = (
                f"Hey {recipient.split()[0]}! Hope you're having a good day. "
                f"Could you please share the details regarding '{blocker_reason}'? "
                f"I need them to finish up '{responsibility_title}' before the upcoming submission window. "
                f"Thanks a lot!"
            )
            draft_content = CommunicationDraft(
                id=f"draft_{uuid.uuid4().hex[:8]}",
                recipient=recipient,
                channel=channel,
                subject=f"Urgent: Info needed for {responsibility_title}" if channel == SourceChannel.GMAIL else None,
                body=body,
                status=ActionStatus.PROPOSED,
                reason=f"Unblock '{responsibility_title}' ({blocker_reason})",
                related_responsibility_id=responsibility_id,
                created_at=datetime.now()
            )
        else:
            draft_content.id = f"draft_{uuid.uuid4().hex[:8]}"
            draft_content.related_responsibility_id = responsibility_id
            draft_content.status = ActionStatus.PROPOSED

        save_communication_draft(draft_content)

        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="ExecutionAgent",
            activity_type="human_approval_draft_prepared",
            message=f"Prepared communication draft to {recipient}. ⏳ Waiting for human approval.",
            status="action_needed",
            details={
                "draft_id": draft_content.id,
                "recipient": recipient,
                "channel": channel.value,
                "related_task": responsibility_title
            }
        )
        log_agent_event(act_event)

        return draft_content

    def approve_action(self, draft_id: str, responsibility_id: Optional[str] = None) -> None:
        update_draft_status(draft_id, ActionStatus.APPROVED)

        # If this resolves a blocker on a responsibility, unblock it
        if responsibility_id:
            resp = get_responsibility_by_id(responsibility_id)
            if resp:
                resp.is_blocked = False
                resp.status = Status.IN_PROGRESS
                resp.blocker_reason = None
                for act in resp.subactions:
                    act.is_blocked = False
                    act.blocker_reason = None
                save_responsibility(resp)

        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="ExecutionAgent",
            activity_type="action_approved",
            message=f"User approved communication draft '{draft_id}'. Dependency blocker marked resolved.",
            status="success",
            details={"draft_id": draft_id, "responsibility_id": responsibility_id}
        )
        log_agent_event(act_event)

    def reject_action(self, draft_id: str) -> None:
        update_draft_status(draft_id, ActionStatus.REJECTED)
        act_event = AgentActivityEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            agent_name="ExecutionAgent",
            activity_type="action_rejected",
            message=f"User rejected communication draft '{draft_id}'. Action dismissed.",
            status="info",
            details={"draft_id": draft_id}
        )
        log_agent_event(act_event)

    def edit_action(self, draft_id: str, new_body: str, responsibility_id: Optional[str] = None) -> None:
        update_draft_status(draft_id, ActionStatus.EDITED, updated_body=new_body)
        self.approve_action(draft_id, responsibility_id)
