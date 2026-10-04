from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from .enums import (
    EventType,
    PriorityLevel,
    Status,
    DependencyType,
    WorkingPreference,
    ActionStatus,
    SourceChannel,
)

class UserPreference(BaseModel):
    preference: WorkingPreference = WorkingPreference.BALANCED
    daily_available_hours: float = 5.0
    buffer_percent: float = 0.20  # 20% reserved for uncertainty
    focus_block_length_hours: float = 1.5

class SourceMessage(BaseModel):
    id: str
    channel: SourceChannel = SourceChannel.MANUAL
    sender: str
    subject: Optional[str] = None
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    processed: bool = False

class ExtractedEvent(BaseModel):
    event_type: EventType = EventType.INFORMATIONAL
    responsibility_title: str
    action_summary: str
    deadline: Optional[str] = None  # ISO format string or human relative e.g. "Tomorrow 10:00 AM"
    requirements: List[str] = Field(default_factory=list)
    sender_or_source: str = "Unknown"
    urgency_indicators: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    confidence: float = 0.95
    source_reference: Optional[str] = None
    is_ambiguous: bool = False
    ambiguity_notes: Optional[str] = None

class ContextResolution(BaseModel):
    action_type: str  # "create_new", "update_existing", "add_deadline", "change_deadline", "add_dependency", "add_blocker", "duplicate", "irrelevant"
    matched_responsibility_id: Optional[str] = None
    matched_responsibility_title: Optional[str] = None
    reasoning: str
    changes: Dict[str, Any] = Field(default_factory=dict)

class PriorityBreakdown(BaseModel):
    total_score: float = 0.0
    deadline_urgency: float = 0.0      # 25% weight
    consequence: float = 0.0           # 20% weight
    dependency_impact: float = 0.0     # 15% weight
    effort_risk: float = 0.0           # 15% weight
    personal_preference: float = 0.0   # 10% weight
    focus_fit: float = 0.0             # 10% weight
    historical_behavior: float = 0.0   # 5% weight
    explanation_summary: str = ""
    rank: int = 1

class SubAction(BaseModel):
    id: str
    responsibility_id: str
    title: str
    estimated_minutes: int = 30
    status: Status = Status.PENDING
    order_idx: int = 0
    is_blocked: bool = False
    blocker_reason: Optional[str] = None

class Responsibility(BaseModel):
    id: str
    title: str
    category: str = "Academic"  # Academic, Career, Extracurricular, Admin
    description: str = ""
    deadline: Optional[datetime] = None
    deadline_str: Optional[str] = None
    estimated_hours: float = 1.0
    consequence_score: float = 50.0   # 0 to 100
    importance_score: float = 50.0    # 0 to 100
    difficulty_level: int = 3         # 1 (quick win) to 5 (deep heavy)
    status: Status = Status.PENDING
    source_id: Optional[str] = None
    is_blocked: bool = False
    blocker_reason: Optional[str] = None
    subactions: List[SubAction] = Field(default_factory=list)
    priority_breakdown: Optional[PriorityBreakdown] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class DependencyEdge(BaseModel):
    id: str
    from_node: str   # source node ID
    to_node: str     # target node ID
    dependency_type: DependencyType = DependencyType.DEPENDS_ON
    description: str = ""

class ScheduleBlock(BaseModel):
    id: str
    title: str
    responsibility_id: Optional[str] = None
    start_time: str   # e.g. "09:00"
    end_time: str     # e.g. "10:30"
    duration_minutes: int = 90
    block_type: str = "task"   # "task", "buffer", "break"
    priority_score: float = 0.0
    notes: str = ""

class Plan(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=datetime.now)
    preference_mode: WorkingPreference = WorkingPreference.BALANCED
    total_workload_hours: float = 0.0
    available_hours: float = 5.0
    buffer_hours: float = 1.0
    is_overloaded: bool = False
    schedule_blocks: List[ScheduleBlock] = Field(default_factory=list)
    ranked_responsibilities: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""

class PlanDiff(BaseModel):
    previous_plan_id: Optional[str] = None
    new_plan_id: str
    trigger_event: str
    reason: str
    rank_changes: List[Dict[str, Any]] = Field(default_factory=list)
    timeline_changes: List[str] = Field(default_factory=list)
    conflicts_detected: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

class AgentActivityEvent(BaseModel):
    id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_name: str
    activity_type: str
    message: str
    status: str = "success"  # "success", "warning", "info", "action_needed"
    details: Optional[Dict[str, Any]] = None

class CommunicationDraft(BaseModel):
    id: str
    recipient: str
    channel: SourceChannel = SourceChannel.WHATSAPP
    subject: Optional[str] = None
    body: str
    status: ActionStatus = ActionStatus.PROPOSED
    reason: str
    related_responsibility_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

class ConflictAlert(BaseModel):
    severity: str = "warning"  # "critical", "warning", "info"
    conflict_type: str        # "overload", "deadline_collision", "unresolved_dependency"
    message: str
    affected_responsibility_ids: List[str] = Field(default_factory=list)
