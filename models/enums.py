from enum import Enum

class EventType(str, Enum):
    DEADLINE = "deadline"
    ASSIGNMENT = "assignment"
    REQUEST = "request"
    COMMITMENT = "commitment"
    ANNOUNCEMENT = "announcement"
    OPPORTUNITY = "opportunity"
    REMINDER = "reminder"
    DEPENDENCY = "dependency"
    BLOCKER = "blocker"
    INFORMATIONAL = "informational"
    IRRELEVANT = "irrelevant"

class PriorityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Status(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    DEFERRED = "deferred"

class DependencyType(str, Enum):
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    BLOCKED_BY = "blocked_by"
    DERIVED_FROM = "derived_from"
    DEADLINE_FOR = "deadline_for"
    RELATED_TO = "related_to"

class WorkingPreference(str, Enum):
    DEADLINE_FIRST = "Deadline-first"
    DIFFICULTY_FIRST = "Difficulty-first"
    QUICK_WINS = "Quick-wins"
    DEEP_WORK = "Deep-work"
    BALANCED = "Balanced"

class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    EXECUTED = "executed"

class SourceChannel(str, Enum):
    GMAIL = "Gmail"
    WHATSAPP = "WhatsApp"
    CLASSROOM = "Google Classroom"
    PORTAL = "College Portal"
    MANUAL = "Manual Note"
    DEMO = "Demo Simulator"
