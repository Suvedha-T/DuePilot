import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from .schema import SCHEMA_SQL
from models.schemas import (
    UserPreference,
    SourceMessage,
    Responsibility,
    SubAction,
    DependencyEdge,
    Plan,
    ScheduleBlock,
    PlanDiff,
    AgentActivityEvent,
    CommunicationDraft,
    PriorityBreakdown,
)
from models.enums import (
    WorkingPreference,
    Status,
    ActionStatus,
    DependencyType,
    SourceChannel,
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db")

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: str = DB_PATH) -> None:
    conn = get_db_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        # Ensure default user
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = 'user_default'")
        if not cur.fetchone():
            cur.execute("INSERT INTO users (id, name, email) VALUES ('user_default', 'Student Pilot', 'pilot@campus.edu')")
            cur.execute(
                "INSERT INTO preferences (user_id, preference, daily_available_hours, buffer_percent, focus_block_length_hours) "
                "VALUES ('user_default', 'Balanced', 5.0, 0.20, 1.5)"
            )
        conn.commit()
    finally:
        conn.close()

def reset_db(db_path: str = DB_PATH) -> None:
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass
    init_db(db_path)

# --- Preferences ---
def get_user_preference(user_id: str = "user_default") -> UserPreference:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT preference, daily_available_hours, buffer_percent, focus_block_length_hours FROM preferences WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return UserPreference(
                preference=WorkingPreference(row["preference"]),
                daily_available_hours=row["daily_available_hours"],
                buffer_percent=row["buffer_percent"],
                focus_block_length_hours=row["focus_block_length_hours"],
            )
        return UserPreference()
    finally:
        conn.close()

def update_user_preference(pref: UserPreference, user_id: str = "user_default") -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO preferences (user_id, preference, daily_available_hours, buffer_percent, focus_block_length_hours, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                preference = excluded.preference,
                daily_available_hours = excluded.daily_available_hours,
                buffer_percent = excluded.buffer_percent,
                focus_block_length_hours = excluded.focus_block_length_hours,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, pref.preference.value, pref.daily_available_hours, pref.buffer_percent, pref.focus_block_length_hours)
        )
        conn.commit()
    finally:
        conn.close()

# --- Responsibilities & Actions ---
def save_responsibility(resp: Responsibility) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        p_score = resp.priority_breakdown.total_score if resp.priority_breakdown else 0.0
        p_json = resp.priority_breakdown.model_dump_json() if resp.priority_breakdown else None
        deadline_iso = resp.deadline.isoformat() if resp.deadline else None

        cur.execute(
            """
            INSERT INTO responsibilities (
                id, title, category, description, deadline, deadline_str,
                estimated_hours, consequence_score, importance_score,
                difficulty_level, status, source_id, is_blocked, blocker_reason,
                priority_score, priority_data_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                description = excluded.description,
                deadline = excluded.deadline,
                deadline_str = excluded.deadline_str,
                estimated_hours = excluded.estimated_hours,
                consequence_score = excluded.consequence_score,
                importance_score = excluded.importance_score,
                difficulty_level = excluded.difficulty_level,
                status = excluded.status,
                source_id = excluded.source_id,
                is_blocked = excluded.is_blocked,
                blocker_reason = excluded.blocker_reason,
                priority_score = excluded.priority_score,
                priority_data_json = excluded.priority_data_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                resp.id, resp.title, resp.category, resp.description, deadline_iso, resp.deadline_str,
                resp.estimated_hours, resp.consequence_score, resp.importance_score,
                resp.difficulty_level, resp.status.value, resp.source_id, 1 if resp.is_blocked else 0,
                resp.blocker_reason, p_score, p_json, resp.created_at.isoformat()
            )
        )

        # Update subactions
        cur.execute("DELETE FROM actions WHERE responsibility_id = ?", (resp.id,))
        for action in resp.subactions:
            cur.execute(
                """
                INSERT INTO actions (id, responsibility_id, title, estimated_minutes, status, order_idx, is_blocked, blocker_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (action.id, resp.id, action.title, action.estimated_minutes, action.status.value, action.order_idx, 1 if action.is_blocked else 0, action.blocker_reason)
            )
        conn.commit()
    finally:
        conn.close()

def get_responsibilities(status_filter: Optional[Status] = None) -> List[Responsibility]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM responsibilities"
        params = []
        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter.value)
        query += " ORDER BY priority_score DESC, deadline ASC"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        responsibilities = []
        for r in rows:
            # fetch subactions
            cur.execute("SELECT * FROM actions WHERE responsibility_id = ? ORDER BY order_idx ASC", (r["id"],))
            action_rows = cur.fetchall()
            subactions = [
                SubAction(
                    id=a["id"],
                    responsibility_id=a["responsibility_id"],
                    title=a["title"],
                    estimated_minutes=a["estimated_minutes"],
                    status=Status(a["status"]),
                    order_idx=a["order_idx"],
                    is_blocked=bool(a["is_blocked"]),
                    blocker_reason=a["blocker_reason"]
                )
                for a in action_rows
            ]

            p_breakdown = None
            if r["priority_data_json"]:
                try:
                    p_breakdown = PriorityBreakdown.model_validate_json(r["priority_data_json"])
                except Exception:
                    pass

            deadline_dt = datetime.fromisoformat(r["deadline"]) if r["deadline"] else None

            responsibilities.append(
                Responsibility(
                    id=r["id"],
                    title=r["title"],
                    category=r["category"],
                    description=r["description"] or "",
                    deadline=deadline_dt,
                    deadline_str=r["deadline_str"],
                    estimated_hours=r["estimated_hours"],
                    consequence_score=r["consequence_score"],
                    importance_score=r["importance_score"],
                    difficulty_level=r["difficulty_level"],
                    status=Status(r["status"]),
                    source_id=r["source_id"],
                    is_blocked=bool(r["is_blocked"]),
                    blocker_reason=r["blocker_reason"],
                    subactions=subactions,
                    priority_breakdown=p_breakdown,
                    created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else datetime.now(),
                    updated_at=datetime.fromisoformat(r["updated_at"]) if r["updated_at"] else datetime.now(),
                )
            )
        return responsibilities
    finally:
        conn.close()

def get_responsibility_by_id(resp_id: str) -> Optional[Responsibility]:
    resps = get_responsibilities()
    for r in resps:
        if r.id == resp_id:
            return r
    return None

def delete_responsibility(resp_id: str) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM actions WHERE responsibility_id = ?", (resp_id,))
        cur.execute("DELETE FROM dependencies WHERE from_node = ? OR to_node = ?", (resp_id, resp_id))
        cur.execute("DELETE FROM responsibilities WHERE id = ?", (resp_id,))
        conn.commit()
    finally:
        conn.close()

# --- Dependencies ---
def save_dependency(edge: DependencyEdge) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO dependencies (id, from_node, to_node, dependency_type, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (edge.id, edge.from_node, edge.to_node, edge.dependency_type.value, edge.description)
        )
        conn.commit()
    finally:
        conn.close()

def get_dependencies() -> List[DependencyEdge]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM dependencies")
        rows = cur.fetchall()
        return [
            DependencyEdge(
                id=r["id"],
                from_node=r["from_node"],
                to_node=r["to_node"],
                dependency_type=DependencyType(r["dependency_type"]),
                description=r["description"] or "",
            )
            for r in rows
        ]
    finally:
        conn.close()

# --- Plans ---
def save_plan(plan: Plan) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        plan_json = plan.model_dump_json()
        cur.execute(
            """
            INSERT OR REPLACE INTO plans (
                id, created_at, preference_mode, total_workload_hours,
                available_hours, buffer_hours, is_overloaded, plan_data_json, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.id, plan.created_at.isoformat(), plan.preference_mode.value,
                plan.total_workload_hours, plan.available_hours, plan.buffer_hours,
                1 if plan.is_overloaded else 0, plan_json, plan.summary
            )
        )
        cur.execute("DELETE FROM schedule_blocks WHERE plan_id = ?", (plan.id,))
        for b in plan.schedule_blocks:
            cur.execute(
                """
                INSERT INTO schedule_blocks (
                    id, plan_id, title, responsibility_id, start_time, end_time,
                    duration_minutes, block_type, priority_score, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (b.id, plan.id, b.title, b.responsibility_id, b.start_time, b.end_time, b.duration_minutes, b.block_type, b.priority_score, b.notes)
            )
        conn.commit()
    finally:
        conn.close()

def get_latest_plan() -> Optional[Plan]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT plan_data_json FROM plans ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if row and row["plan_data_json"]:
            return Plan.model_validate_json(row["plan_data_json"])
        return None
    finally:
        conn.close()

# --- Plan Diffs ---
def save_plan_diff(diff: PlanDiff) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO plan_diffs (id, previous_plan_id, new_plan_id, trigger_event, reason, diff_data_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"diff_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                diff.previous_plan_id,
                diff.new_plan_id,
                diff.trigger_event,
                diff.reason,
                diff.model_dump_json(),
                diff.created_at.isoformat()
            )
        )
        conn.commit()
    finally:
        conn.close()

def get_latest_plan_diff() -> Optional[PlanDiff]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT diff_data_json FROM plan_diffs ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if row and row["diff_data_json"]:
            return PlanDiff.model_validate_json(row["diff_data_json"])
        return None
    finally:
        conn.close()

# --- Agent Events ---
def log_agent_event(event: AgentActivityEvent) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO agent_events (id, timestamp, agent_name, activity_type, message, status, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.timestamp.isoformat(),
                event.agent_name,
                event.activity_type,
                event.message,
                event.status,
                json.dumps(event.details) if event.details else None
            )
        )
        conn.commit()
    finally:
        conn.close()

def get_agent_events(limit: int = 50) -> List[AgentActivityEvent]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM agent_events ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        events = []
        for r in rows:
            events.append(
                AgentActivityEvent(
                    id=r["id"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    agent_name=r["agent_name"],
                    activity_type=r["activity_type"],
                    message=r["message"],
                    status=r["status"],
                    details=json.loads(r["details_json"]) if r["details_json"] else None
                )
            )
        return events
    finally:
        conn.close()

# --- Communication Drafts ---
def save_communication_draft(draft: CommunicationDraft) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO communication_drafts (
                id, recipient, channel, subject, body, status, reason, related_responsibility_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.id, draft.recipient, draft.channel.value, draft.subject,
                draft.body, draft.status.value, draft.reason, draft.related_responsibility_id,
                draft.created_at.isoformat()
            )
        )
        conn.commit()
    finally:
        conn.close()

def get_communication_drafts() -> List[CommunicationDraft]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM communication_drafts ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [
            CommunicationDraft(
                id=r["id"],
                recipient=r["recipient"],
                channel=SourceChannel(r["channel"]),
                subject=r["subject"],
                body=r["body"],
                status=ActionStatus(r["status"]),
                reason=r["reason"],
                related_responsibility_id=r["related_responsibility_id"],
                created_at=datetime.fromisoformat(r["created_at"])
            )
            for r in rows
        ]
    finally:
        conn.close()

def update_draft_status(draft_id: str, new_status: ActionStatus, updated_body: Optional[str] = None) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if updated_body is not None:
            cur.execute("UPDATE communication_drafts SET status = ?, body = ? WHERE id = ?", (new_status.value, updated_body, draft_id))
        else:
            cur.execute("UPDATE communication_drafts SET status = ? WHERE id = ?", (new_status.value, draft_id))
        conn.commit()
    finally:
        conn.close()
