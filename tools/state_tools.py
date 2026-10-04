from typing import List, Optional, Dict, Any
from models.schemas import Responsibility, Plan, DependencyEdge, CommunicationDraft, UserPreference
from models.enums import Status, DependencyType, SourceChannel, ActionStatus
from database.database import (
    get_responsibilities,
    get_responsibility_by_id,
    save_responsibility,
    get_latest_plan,
    save_plan,
    save_dependency,
    get_dependencies,
    save_communication_draft,
    get_user_preference,
)
from core.priority_engine import PriorityEngine
from core.planner import Planner

def tool_get_current_responsibilities(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Tool: Retrieve active commitments from SQLite."""
    st = Status(status_filter) if status_filter else None
    resps = get_responsibilities(st)
    return [r.model_dump() for r in resps]

def tool_get_current_plan() -> Optional[Dict[str, Any]]:
    """Tool: Retrieve current active schedule plan."""
    plan = get_latest_plan()
    return plan.model_dump() if plan else None

def tool_create_responsibility(
    title: str,
    category: str = "Academic",
    estimated_hours: float = 1.0,
    deadline_str: Optional[str] = None,
    consequence_score: float = 50.0
) -> Dict[str, Any]:
    """Tool: Add new commitment to Responsibility Graph."""
    import uuid
    from datetime import datetime
    new_r = Responsibility(
        id=f"resp_{uuid.uuid4().hex[:8]}",
        title=title,
        category=category,
        estimated_hours=estimated_hours,
        deadline_str=deadline_str,
        consequence_score=consequence_score,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    save_responsibility(new_r)
    return new_r.model_dump()

def tool_update_responsibility(resp_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Tool: Mutate fields of an existing responsibility."""
    from datetime import datetime
    r = get_responsibility_by_id(resp_id)
    if not r:
        return None
    for k, v in updates.items():
        if hasattr(r, k):
            setattr(r, k, v)
    r.updated_at = datetime.now()
    save_responsibility(r)
    return r.model_dump()

def tool_create_dependency(from_node: str, to_node: str, dep_type: str = "depends_on", description: str = "") -> Dict[str, Any]:
    """Tool: Link two nodes with a dependency edge."""
    import uuid
    edge = DependencyEdge(
        id=f"dep_{uuid.uuid4().hex[:8]}",
        from_node=from_node,
        to_node=to_node,
        dependency_type=DependencyType(dep_type),
        description=description
    )
    save_dependency(edge)
    return edge.model_dump()

def tool_calculate_priority(resp_id: str) -> Optional[Dict[str, Any]]:
    """Tool: Calculate deterministic priority breakdown for a commitment."""
    r = get_responsibility_by_id(resp_id)
    if not r:
        return None
    pref = get_user_preference()
    breakdown = PriorityEngine.calculate_priority(r, pref)
    r.priority_breakdown = breakdown
    save_responsibility(r)
    return breakdown.model_dump()

def tool_generate_plan() -> Dict[str, Any]:
    """Tool: Trigger daily focus schedule synthesis."""
    pref = get_user_preference()
    resps = get_responsibilities()
    ranked = PriorityEngine.rank_responsibilities(resps, pref)
    for r in ranked:
        save_responsibility(r)
    plan = Planner.generate_plan(ranked, pref)
    save_plan(plan)
    return plan.model_dump()

def tool_generate_communication_draft(
    responsibility_id: str,
    recipient: str,
    reason: str,
    channel: str = "WhatsApp",
    body_text: Optional[str] = None
) -> Dict[str, Any]:
    """Tool: Generate a communication draft for human approval."""
    import uuid
    from datetime import datetime
    r = get_responsibility_by_id(responsibility_id)
    r_title = r.title if r else "Task"
    body = body_text or f"Hi {recipient.split()[0]}, could you please send the details needed for {r_title}?"
    draft = CommunicationDraft(
        id=f"draft_{uuid.uuid4().hex[:8]}",
        recipient=recipient,
        channel=SourceChannel(channel),
        body=body,
        status=ActionStatus.PROPOSED,
        reason=reason,
        related_responsibility_id=responsibility_id,
        created_at=datetime.now()
    )
    save_communication_draft(draft)
    return draft.model_dump()
