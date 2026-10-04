from typing import List, Optional
from datetime import datetime, timedelta
from models.schemas import Responsibility, PriorityBreakdown, UserPreference
from models.enums import WorkingPreference, Status

class PriorityEngine:
    WEIGHT_DEADLINE = 25.0
    WEIGHT_CONSEQUENCE = 20.0
    WEIGHT_DEPENDENCY = 15.0
    WEIGHT_EFFORT_RISK = 15.0
    WEIGHT_PREFERENCE = 10.0
    WEIGHT_FOCUS_FIT = 10.0
    WEIGHT_HISTORICAL = 5.0

    @classmethod
    def calculate_priority(
        cls,
        resp: Responsibility,
        user_pref: UserPreference,
        dependent_count: int = 0,
        now: Optional[datetime] = None
    ) -> PriorityBreakdown:
        if now is None:
            now = datetime.now()

        # 1. Deadline Urgency (0 - 25)
        deadline_pts = 0.0
        days_left = 999.0
        if resp.deadline:
            diff_seconds = (resp.deadline - now).total_seconds()
            days_left = max(0.0, diff_seconds / 86400.0)
            if diff_seconds <= 0:
                deadline_pts = cls.WEIGHT_DEADLINE
            elif days_left <= 0.5:  # within 12 hours
                deadline_pts = cls.WEIGHT_DEADLINE
            elif days_left <= 1.0:  # within 24 hours
                deadline_pts = cls.WEIGHT_DEADLINE * 0.95
            elif days_left <= 2.0:  # 2 days
                deadline_pts = cls.WEIGHT_DEADLINE * 0.80
            elif days_left <= 3.0:  # 3 days
                deadline_pts = cls.WEIGHT_DEADLINE * 0.60
            elif days_left <= 5.0:  # 5 days
                deadline_pts = cls.WEIGHT_DEADLINE * 0.35
            else:
                deadline_pts = max(2.0, cls.WEIGHT_DEADLINE * 0.15)
        else:
            deadline_pts = 5.0  # open-ended default

        # 2. Consequence (0 - 20)
        consequence_pts = (max(0.0, min(100.0, resp.consequence_score)) / 100.0) * cls.WEIGHT_CONSEQUENCE

        # 3. Dependency Impact (0 - 15)
        # If this task blocks others, it is high priority. If it is blocked, it cannot be run immediately.
        dependency_pts = 0.0
        if resp.is_blocked:
            # Blocked task cannot be worked on directly, so operational execution readiness is lower
            dependency_pts = 2.0
        elif dependent_count > 0:
            dependency_pts = min(cls.WEIGHT_DEPENDENCY, 8.0 + (dependent_count * 3.5))
        else:
            dependency_pts = 5.0

        # 4. Effort Risk (0 - 15)
        # Ratio of task duration to remaining time window
        effort_pts = 0.0
        if days_left <= 2.0 and resp.estimated_hours >= 2.0:
            effort_pts = cls.WEIGHT_EFFORT_RISK
        elif days_left <= 3.0 and resp.estimated_hours >= 3.0:
            effort_pts = cls.WEIGHT_EFFORT_RISK * 0.85
        elif resp.estimated_hours >= 4.0:
            effort_pts = cls.WEIGHT_EFFORT_RISK * 0.70
        else:
            effort_pts = (min(resp.estimated_hours, 3.0) / 3.0) * (cls.WEIGHT_EFFORT_RISK * 0.6)

        # 5. Personal Preference (0 - 10)
        pref_pts = 0.0
        pref = user_pref.preference
        if pref == WorkingPreference.DEADLINE_FIRST:
            if days_left <= 1.5:
                pref_pts = cls.WEIGHT_PREFERENCE
            elif days_left <= 3.0:
                pref_pts = cls.WEIGHT_PREFERENCE * 0.7
            else:
                pref_pts = cls.WEIGHT_PREFERENCE * 0.3
        elif pref == WorkingPreference.DIFFICULTY_FIRST:
            pref_pts = (resp.difficulty_level / 5.0) * cls.WEIGHT_PREFERENCE
        elif pref == WorkingPreference.QUICK_WINS:
            if resp.estimated_hours <= 1.0 or resp.difficulty_level <= 2:
                pref_pts = cls.WEIGHT_PREFERENCE
            else:
                pref_pts = cls.WEIGHT_PREFERENCE * 0.3
        elif pref == WorkingPreference.DEEP_WORK:
            if resp.estimated_hours >= 2.0 and resp.difficulty_level >= 3:
                pref_pts = cls.WEIGHT_PREFERENCE
            else:
                pref_pts = cls.WEIGHT_PREFERENCE * 0.4
        else:  # BALANCED
            pref_pts = cls.WEIGHT_PREFERENCE * 0.75

        # 6. Focus Fit (0 - 10)
        # Match between estimated hours and user focus block
        block_len = user_pref.focus_block_length_hours
        ratio = resp.estimated_hours / max(0.5, block_len)
        if 0.7 <= ratio <= 1.3:
            focus_pts = cls.WEIGHT_FOCUS_FIT  # Clean fit in one block
        elif ratio < 0.7:
            focus_pts = cls.WEIGHT_FOCUS_FIT * 0.7  # Small task
        else:
            focus_pts = cls.WEIGHT_FOCUS_FIT * 0.6  # Needs multi-block splitting

        # 7. Historical Behavior (0 - 5)
        # Default baseline reliability
        hist_pts = 4.0

        total = round(deadline_pts + consequence_pts + dependency_pts + effort_pts + pref_pts + focus_pts + hist_pts, 1)
        total = max(0.0, min(100.0, total))

        # Generate concise explainable factors
        reasons = []
        if deadline_pts >= 18.0:
            reasons.append(f"Imminent deadline ({days_left:.1f}d remaining: +{deadline_pts:.1f})")
        if consequence_pts >= 14.0:
            reasons.append(f"High consequence outcome (+{consequence_pts:.1f})")
        if resp.is_blocked:
            reasons.append("⚠️ Currently blocked by external dependency")
        elif dependent_count > 0:
            reasons.append(f"Blocks {dependent_count} downstream task(s) (+{dependency_pts:.1f})")
        if effort_pts >= 10.0:
            reasons.append(f"Heavy effort window ({resp.estimated_hours}h needed: +{effort_pts:.1f})")
        if pref_pts >= 7.5:
            reasons.append(f"Matches '{pref.value}' preference (+{pref_pts:.1f})")

        explanation = "; ".join(reasons) if reasons else "Standard priority based on balanced schedule factors."

        return PriorityBreakdown(
            total_score=total,
            deadline_urgency=round(deadline_pts, 1),
            consequence=round(consequence_pts, 1),
            dependency_impact=round(dependency_pts, 1),
            effort_risk=round(effort_pts, 1),
            personal_preference=round(pref_pts, 1),
            focus_fit=round(focus_pts, 1),
            historical_behavior=round(hist_pts, 1),
            explanation_summary=explanation,
            rank=1
        )

    @classmethod
    def rank_responsibilities(
        cls,
        responsibilities: List[Responsibility],
        user_pref: UserPreference,
        dependency_map: Optional[dict] = None
    ) -> List[Responsibility]:
        if not responsibilities:
            return []

        dep_counts = {}
        if dependency_map:
            for from_node in dependency_map:
                dep_counts[from_node] = len(dependency_map[from_node])

        scored = []
        for r in responsibilities:
            dep_cnt = dep_counts.get(r.id, 0)
            breakdown = cls.calculate_priority(r, user_pref, dependent_count=dep_cnt)
            r.priority_breakdown = breakdown
            scored.append(r)

        # Sort: unblocked first if possible, then by total score descending
        # Notice: blocked tasks shouldn't be executed first unless user resolves blocker
        def sort_key(item: Responsibility):
            score = item.priority_breakdown.total_score if item.priority_breakdown else 0.0
            # If blocked, give slight operational penalty for "what should I do next" actionability
            operational_score = score - (30.0 if item.is_blocked else 0.0)
            return operational_score

        scored.sort(key=sort_key, reverse=True)

        for i, item in enumerate(scored, 1):
            if item.priority_breakdown:
                item.priority_breakdown.rank = i

        return scored
