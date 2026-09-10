"""
StudyFlow/assignments.py
The logic behind the Add Assignment form, kept out of the page and
the State so it can be tested on its own.

Two jobs:
  validate_form()  -> a message per field that is wrong, or none
  build_row()      -> the dict the dashboard renders for one assignment

For now the row is only held in Reflex state. The next step is to
turn the same validated values into a real models.Assignment and
save it through storage.py; nothing here needs to change for that
beyond calling those modules.
"""

from datetime import date, datetime
from typing import Dict, Iterable, List

from models import Assignment, Priority

# The form's priority choices are the Priority enum's names, in order,
# so a submitted value maps straight to Priority[value].
PRIORITIES = [p.name for p in Priority]
FIELDS = ["name", "subject", "due", "hours", "priority"]

# Shown until the scheduler has run; the risk badge falls back to grey.
RISK_NOT_RATED = "NOT RATED"


def no_errors() -> Dict[str, str]:
    """An error dict with every field present and empty."""
    return {field: "" for field in FIELDS}


def validate_form(name: str, subject: str, due: str, hours: str, priority: str) -> Dict[str, str]:
    """
    Check every field and return a message for each one that is wrong.
    Every field is always a key, so the page can bind to it directly;
    a field with no problem has an empty string.
    """
    errors = no_errors()
    if not name.strip():
        errors["name"] = "Give the assignment a name."
    if not subject.strip():
        errors["subject"] = "Enter the subject."
    if parse_due(due) is None:
        errors["due"] = "Choose a due date."
    hours_value = parse_hours(hours)
    if hours_value is None:
        errors["hours"] = "Enter the hours as a number, such as 1.5."
    elif hours_value < 0:
        errors["hours"] = "Hours cannot be negative."
    if priority not in PRIORITIES:
        errors["priority"] = "Choose a priority."
    return errors


def is_valid(errors: Dict[str, str]) -> bool:
    return not any(errors.values())


def parse_due(due: str):
    """'2026-09-15' -> date, or None if it is not a date."""
    try:
        return datetime.strptime(due.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_hours(hours: str):
    """'2.5' -> 2.5, or None if it is not a number."""
    try:
        return float(hours.strip())
    except ValueError:
        return None


def due_in_words(days: int) -> str:
    if days < 0:
        return f"Overdue by {-days} day{'s' if days != -1 else ''}"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"Due in {days} days"


def hours_in_words(hours: float) -> str:
    return "1 hour" if hours == 1 else f"{hours:g} hours"


def to_assignment(name: str, subject: str, due: str, hours: str, priority: str) -> Assignment:
    """
    Turn the validated form strings into a real models.Assignment,
    ready for storage.add_assignment(). Call validate_form() first;
    this assumes the values are good.
    """
    return Assignment(
        name=name.strip(),
        subject=subject.strip(),
        due_date=parse_due(due),
        estimated_hours=parse_hours(hours),
        priority=Priority[priority],
        completed=False,
    )


def row_from_assignment(a: Assignment, today: date) -> Dict[str, str]:
    """
    The dashboard's row for one stored assignment: every value a
    string, plus the id so later features can edit or delete it.
    """
    days = (a.due_date - today).days
    return {
        "id": str(a.id) if a.id is not None else "",
        "name": a.name,
        "subject": a.subject,
        "due": due_in_words(days),
        "due_date": a.due_date.isoformat(),               # for editing
        "due_pretty": a.due_date.strftime("%d %b %Y"),   # "12 Sep 2026", for reading
        "due_in_days": str(max(days, 0)),
        "hours": hours_in_words(a.estimated_hours),
        "priority": a.priority.name,
        "risk": RISK_NOT_RATED,
    }


def rows_from(assignments: Iterable[Assignment], today: date) -> List[Dict[str, str]]:
    """Rows for the dashboard, in the order storage returned them (soonest due first)."""
    return [row_from_assignment(a, today) for a in assignments]


def build_row(name: str, subject: str, due: str, hours: str, priority: str, today: date) -> Dict[str, str]:
    """The row the form's values would show as, without saving. Used by tests."""
    return row_from_assignment(to_assignment(name, subject, due, hours, priority), today)


def sorted_by_urgency(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Soonest due first. Stable, so equal days keep their order."""
    return sorted(rows, key=lambda r: int(r["due_in_days"]))


def total_hours(rows: List[Dict[str, str]]) -> float:
    """Sum of the estimated hours shown on the rows."""
    return sum(float(r["hours"].split()[0]) for r in rows)
