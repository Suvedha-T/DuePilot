from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
from models.schemas import Responsibility, Plan, ScheduleBlock, UserPreference
from models.enums import WorkingPreference, Status

class Planner:
    @classmethod
    def generate_plan(
        cls,
        ranked_responsibilities: List[Responsibility],
        user_pref: UserPreference,
        start_hour: int = 9,
        start_minute: int = 0
    ) -> Plan:
        daily_available = user_pref.daily_available_hours
        buffer_percent = user_pref.buffer_percent
        buffer_budget = daily_available * buffer_percent
        usable_budget = daily_available - buffer_budget

        schedule_blocks: List[ScheduleBlock] = []
        current_time = datetime.now().replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)

        accumulated_work_hours = 0.0
        total_workload = sum(r.estimated_hours for r in ranked_responsibilities if r.status != Status.COMPLETED)
        is_overloaded = total_workload > daily_available

        ranked_meta = []

        # Iterate through ranked responsibilities
        for r in ranked_responsibilities:
            if r.status == Status.COMPLETED:
                continue

            score = r.priority_breakdown.total_score if r.priority_breakdown else 0.0
            rank = r.priority_breakdown.rank if r.priority_breakdown else len(ranked_meta) + 1

            ranked_meta.append({
                "id": r.id,
                "title": r.title,
                "rank": rank,
                "priority_score": score,
                "estimated_hours": r.estimated_hours,
                "is_blocked": r.is_blocked,
                "deadline_str": r.deadline_str
            })

            # If task is blocked, we note it in meta but don't schedule direct execution block
            if r.is_blocked:
                continue

            # Check if we still have usable budget for today's primary plan
            if accumulated_work_hours >= usable_budget:
                # Outside today's scheduled primary window
                continue

            # Determine scheduled duration for this task today
            # If task is 2.5h and fits within remaining budget, schedule it.
            # If it exceeds remaining usable budget, clamp or split.
            remaining_today = usable_budget - accumulated_work_hours
            task_duration_hours = min(r.estimated_hours, remaining_today)
            duration_minutes = int(round(task_duration_hours * 60))

            if duration_minutes <= 0:
                continue

            end_time = current_time + timedelta(minutes=duration_minutes)

            # Add Task Block
            block_id = f"block_{uuid.uuid4().hex[:8]}"
            schedule_blocks.append(
                ScheduleBlock(
                    id=block_id,
                    title=r.title,
                    responsibility_id=r.id,
                    start_time=current_time.strftime("%H:%M"),
                    end_time=end_time.strftime("%H:%M"),
                    duration_minutes=duration_minutes,
                    block_type="task",
                    priority_score=score,
                    notes=f"Priority {score:.0f}/100. Category: {r.category}. Deadline: {r.deadline_str or 'Flexible'}"
                )
            )

            accumulated_work_hours += task_duration_hours
            current_time = end_time

            # Insert buffer block if there is room and task was at least 60 minutes
            if duration_minutes >= 60 and buffer_budget > 0:
                buffer_mins = min(20, int(buffer_budget * 60 / 2))
                buf_end = current_time + timedelta(minutes=buffer_mins)
                schedule_blocks.append(
                    ScheduleBlock(
                        id=f"buf_{uuid.uuid4().hex[:8]}",
                        title="Uncertainty Buffer & Cognitive Recovery",
                        responsibility_id=None,
                        start_time=current_time.strftime("%H:%M"),
                        end_time=buf_end.strftime("%H:%M"),
                        duration_minutes=buffer_mins,
                        block_type="buffer",
                        priority_score=0.0,
                        notes="Protected buffer to absorb task overruns and prevent schedule collapse."
                    )
                )
                current_time = buf_end

        # Summary statement
        summary = (
            f"Generated personalized plan under '{user_pref.preference.value}' mode. "
            f"Scheduled {accumulated_work_hours:.1f}h of high-impact focus with "
            f"{buffer_budget:.1f}h reserved buffer from a total {daily_available:.1f}h available capacity."
        )
        if is_overloaded:
            summary += f" ⚠️ Total active workload ({total_workload:.1f}h) exceeds daily budget. Defer low-priority items."

        plan_id = f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return Plan(
            id=plan_id,
            created_at=datetime.now(),
            preference_mode=user_pref.preference,
            total_workload_hours=round(total_workload, 1),
            available_hours=daily_available,
            buffer_hours=round(buffer_budget, 1),
            is_overloaded=is_overloaded,
            schedule_blocks=schedule_blocks,
            ranked_responsibilities=ranked_meta,
            summary=summary
        )
