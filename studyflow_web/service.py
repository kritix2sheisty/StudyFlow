"""
studyflow_web/service.py
The seam between the web UI and the StudyFlow engine.

Every function here does one thing the UI needs: read the student's
data, change it, or build the plan, and hand back plain dicts of
strings that a page can render without knowing about dataclasses.
No scheduling or analysis logic lives here; it all comes from the
engine modules.

Why a seam: today StudyFlow is one student on one SQLite file. For a
school it becomes many students, each seeing only their own data.
When that arrives, these functions gain a `student` argument and the
pages stay the same. Keep that in mind when adding to this file: the
UI should never touch storage directly.
"""

from datetime import date, datetime
from typing import Dict, List, Optional

import storage
from models import Assignment, Priority, TimeSlot, Weekday
from schedule_analyzer import analyze_assignments
from schedule_builder import BREAK_LABEL
from schedule_optimizer import deadline_risk_ratio, risk_level
from study_plan import generate_study_plan

Row = Dict[str, str]

WEEKDAYS = [d.name.lower() for d in Weekday]
PRIORITIES = {"1": "Low", "2": "Medium", "3": "High"}
PRIORITY_KEYS = {label: key for key, label in PRIORITIES.items()}


# ---------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------

def _due_in_words(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return f"{-days} day{'s' if days != -1 else ''} overdue"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def _assignment_row(a: Assignment, today: date) -> Row:
    return {
        "id": str(a.id),
        "name": a.name,
        "subject": a.subject,
        "due": a.due_date.isoformat(),
        "due_in": _due_in_words(a.due_date, today),
        "hours": f"{a.estimated_hours:g}",
        "priority": a.priority.name.title(),
        "completed": "yes" if a.completed else "no",
    }


def list_assignments(today: Optional[date] = None) -> List[Row]:
    today = today or date.today()
    return [_assignment_row(a, today) for a in storage.list_assignments()]


def add_assignment(name: str, subject: str, due: str, hours: str, priority: str) -> Optional[str]:
    """Validate and store. Returns an error message, or None on success."""
    name, subject = name.strip(), subject.strip()
    if not name:
        return "Give the assignment a name."
    try:
        due_date = datetime.strptime(due.strip(), "%Y-%m-%d").date()
    except ValueError:
        return "Due date must be YYYY-MM-DD."
    try:
        estimated = float(hours)
    except ValueError:
        return "Estimated hours must be a number."
    if estimated < 0:
        return "Estimated hours cannot be negative."
    priority = PRIORITY_KEYS.get(priority.strip().title(), priority.strip())   # accept "High" or "3"
    if priority not in PRIORITIES:
        return "Choose a priority."
    storage.add_assignment(Assignment(
        name=name, subject=subject, due_date=due_date,
        estimated_hours=estimated, priority=Priority(int(priority)),
    ))
    return None


def toggle_assignment(assignment_id: str) -> None:
    existing = next((a for a in storage.list_assignments() if str(a.id) == assignment_id), None)
    if existing:
        storage.mark_assignment_complete(existing.id, not existing.completed)


def delete_assignment(assignment_id: str) -> None:
    storage.delete_assignment(int(assignment_id))


# ---------------------------------------------------------------------
# Study time
# ---------------------------------------------------------------------

def _slot_row(s: TimeSlot) -> Row:
    return {
        "id": str(s.id),
        "weekday": s.weekday.name.title(),
        "time": str(s).split(" ", 1)[1],   # "4 PM–6 PM (2h)"
    }


def list_slots() -> List[Row]:
    return [_slot_row(s) for s in storage.list_time_slots()]


def add_slot(weekday: str, start_hour: str, end_hour: str) -> Optional[str]:
    """Validate and store. Returns an error message, or None on success."""
    try:
        day = Weekday.from_name(weekday)
    except KeyError:
        return "Choose a weekday."
    try:
        start, end = int(start_hour), int(end_hour)
    except ValueError:
        return "Hours must be whole numbers on the 24-hour clock."
    if not (0 <= start < end <= 24):
        return "The slot must start before it ends, between 0 and 24."
    storage.add_time_slot(TimeSlot(weekday=day, start_hour=start, end_hour=end))
    return None


def delete_slot(slot_id: str) -> None:
    storage.delete_time_slot(int(slot_id))


# ---------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------

def build_plan(today: Optional[date] = None) -> Dict[str, object]:
    """
    Run the whole pipeline on the stored data and shape it for the
    page: days with their blocks, the progress numbers, and one status
    row per assignment with its deadline risk.
    """
    today = today or date.today()
    assignments = storage.list_assignments(include_completed=False)
    slots = storage.list_time_slots()
    plan = generate_study_plan(assignments, slots, today=today)

    days = []
    for day in sorted(plan.schedule.by_date):
        blocks = plan.schedule.by_date[day]
        days.append({
            "label": day.strftime("%A %d %B"),
            "blocks": [
                {"time": b.format_time_range(), "label": b.label,
                 "is_break": "yes" if b.label == BREAK_LABEL else "no"}
                for b in blocks
            ],
        })

    statuses = []
    for row in analyze_assignments(plan.schedule, assignments):
        ratio = deadline_risk_ratio(row.assignment, plan.schedule, slots, today)
        statuses.append({
            "name": row.assignment.name,
            "status": row.status,
            "scheduled": f"{row.scheduled_hours:.1f}",
            "required": f"{row.required_hours:.1f}",
            "remaining": f"{row.remaining_hours:.1f}",
            "risk": risk_level(ratio) if row.remaining_hours > 0 else "",
            "due": row.assignment.due_date.isoformat(),
        })

    return {
        "today": today.strftime("%A %d %B %Y"),
        "days": days,
        "progress": {
            "required": f"{plan.required_hours:.1f}",
            "scheduled": f"{plan.scheduled_hours:.1f}",
            "unscheduled": f"{plan.unscheduled_hours:.1f}",
            "completion": f"{plan.completion:.0f}",
        },
        "statuses": statuses,
        "at_risk": [a.name for a in plan.at_risk],
        "has_slots": bool(slots),
        "has_assignments": bool(assignments),
    }
