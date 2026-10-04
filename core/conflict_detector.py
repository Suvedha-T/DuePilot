from typing import List, Dict, Any, Optional
from datetime import datetime
from models.schemas import Responsibility, ConflictAlert, UserPreference

class ConflictDetector:
    @classmethod
    def detect_conflicts(
        cls,
        responsibilities: List[Responsibility],
        user_pref: UserPreference,
        now: Optional[datetime] = None
    ) -> List[ConflictAlert]:
        if now is None:
            now = datetime.now()

        alerts: List[ConflictAlert] = []

        # 1. Check for Workload Overload within next 48 hours
        upcoming_workload = 0.0
        urgent_resps = []
        for r in responsibilities:
            if r.status.value in ("completed", "deferred"):
                continue
            days_left = 999.0
            if r.deadline:
                days_left = max(0.0, (r.deadline - now).total_seconds() / 86400.0)
            
            # Count workload due within 48h
            if days_left <= 2.0:
                upcoming_workload += r.estimated_hours
                urgent_resps.append(r)

        daily_budget = user_pref.daily_available_hours
        usable_budget = daily_budget * (1.0 - user_pref.buffer_percent)

        if upcoming_workload > (usable_budget * 2.0):
            alerts.append(
                ConflictAlert(
                    severity="critical",
                    conflict_type="overload",
                    message=(
                        f"⚠️ Workload Overload: {upcoming_workload:.1f}h of work due within 48 hours, "
                        f"exceeding your 2-day usable budget of {usable_budget * 2.0:.1f}h ({daily_budget * 2:.1f}h total with {user_pref.buffer_percent*100:.0f}% buffer). "
                        "Recommendation: Defer low-consequence tasks and protect buffer time."
                    ),
                    affected_responsibility_ids=[r.id for r in urgent_resps]
                )
            )
        elif upcoming_workload > (usable_budget * 1.3):
            alerts.append(
                ConflictAlert(
                    severity="warning",
                    conflict_type="overload",
                    message=(
                        f"⚠️ High Workload Warning: {upcoming_workload:.1f}h needed soon vs {usable_budget:.1f}h daily capacity. "
                        "Buffer time is severely compressed."
                    ),
                    affected_responsibility_ids=[r.id for r in urgent_resps]
                )
            )

        # 2. Check for Deadline Collision (multiple high-consequence items due in <= 24 hours)
        imminent_heavy = [
            r for r in urgent_resps
            if (r.deadline and (r.deadline - now).total_seconds() <= 86400)
            and r.estimated_hours >= 1.5
        ]
        if len(imminent_heavy) >= 2:
            names = ", ".join([f"'{r.title}' ({r.estimated_hours}h)" for r in imminent_heavy])
            combined_hours = sum(r.estimated_hours for r in imminent_heavy)
            alerts.append(
                ConflictAlert(
                    severity="critical",
                    conflict_type="deadline_collision",
                    message=(
                        f"🚨 Imminent Deadline Collision: Multiple heavy commitments due tomorrow ({names}). "
                        f"Combined effort is {combined_hours:.1f}h. Requires strict sequential execution."
                    ),
                    affected_responsibility_ids=[r.id for r in imminent_heavy]
                )
            )

        # 3. Check for Blocked Dependencies on active commitments
        for r in responsibilities:
            if r.is_blocked:
                alerts.append(
                    ConflictAlert(
                        severity="warning",
                        conflict_type="unresolved_dependency",
                        message=f"🔒 Dependency Blocker: '{r.title}' cannot proceed. Reason: {r.blocker_reason or 'Prerequisite pending'}. Action needed to unblock.",
                        affected_responsibility_ids=[r.id]
                    )
                )

        return alerts
