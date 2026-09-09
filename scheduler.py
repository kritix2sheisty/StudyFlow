"""
scheduler.py
Phase 2 — prioritization logic for StudyFlow.

This does NOT build a full schedule yet (that's Phase 3, matching
assignments to actual time slots). It answers a narrower question:
"if I can only work on one thing next, what should it be?"
"""

from datetime import date
from typing import List, Optional

from models import Assignment

# Tunable weights — how much each factor influences the final score,
# among items that are not overdue (overdue items always sort first;
# see prioritize_assignments below).
DUE_DATE_WEIGHT = 5.0
PRIORITY_WEIGHT = 3.0
EFFORT_WEIGHT = 1.0


def _is_overdue(assignment: Assignment, today: date) -> bool:
    return assignment.due_date <= today


def _urgency_score(assignment: Assignment, today: date) -> float:
    """
    Higher = more time pressure. Decays smoothly as the due date gets
    further away. Only meaningful for non-overdue assignments — see
    _is_overdue, which is checked separately and always wins first.
    """
    days_left = (assignment.due_date - today).days
    return 10.0 / max(days_left, 1)


def _priority_score(assignment: Assignment) -> float:
    """Priority enum is already 1 (LOW) to 3 (HIGH) — use it directly."""
    return float(assignment.priority)


def _effort_score(assignment: Assignment) -> float:
    """
    Bigger tasks get a small boost. Rationale: a 10-hour assignment
    due in 5 days needs to be started sooner than a 1-hour assignment
    due in 5 days, even though their due dates are identical.
    """
    return assignment.estimated_hours


def prioritize_assignments(
    assignments: List[Assignment],
    today: Optional[date] = None,
) -> List[Assignment]:

    """
    Return assignments sorted from most to least urgent.

    Completed assignments are excluded entirely — there's nothing to
    prioritize once something is done.

    Sorting happens in two tiers:
      1. Overdue (or due today) items always come before non-overdue
         items, no matter their priority or size. A blended numeric
         score can't guarantee this reliably (a same-day-due HIGH
         priority item can out-score a barely-overdue LOW priority
         one), so overdue status is checked as its own tier first.
      2. Within each tier, items are ranked by a weighted score
         combining urgency, priority, and effort.

    `today` defaults to date.today() but can be overridden, which is
    what makes this function easy to test (see tests/test_scheduler.py).
    """
    today = today or date.today()
    active = [a for a in assignments if not a.completed]

    def weighted_score(a: Assignment) -> float:
        return (
            _urgency_score(a, today) * DUE_DATE_WEIGHT
            + _priority_score(a) * PRIORITY_WEIGHT
            + _effort_score(a) * EFFORT_WEIGHT
        )

    def sort_key(a: Assignment):
        return (_is_overdue(a, today), weighted_score(a))

    return sorted(active, key=sort_key, reverse=True)