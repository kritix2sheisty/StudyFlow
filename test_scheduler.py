"""
tests/test_scheduler.py
Pytest suite for scheduler.prioritize_assignments().
"""

from datetime import date, timedelta

from models import Assignment, Priority
from scheduler import prioritize_assignments

TODAY = date(2026, 8, 14)


def test_completed_assignments_are_excluded():
    assignments = [
        Assignment(name="Done", subject="Bio", due_date=TODAY, completed=True),
        Assignment(name="Not done", subject="Bio", due_date=TODAY, completed=False),
    ]
    result = prioritize_assignments(assignments, today=TODAY)
    assert [a.name for a in result] == ["Not done"]


def test_overdue_beats_everything_regardless_of_priority():
    assignments = [
        Assignment(name="Overdue, low priority", subject="Art",
                   due_date=TODAY - timedelta(days=3),
                   estimated_hours=1, priority=Priority.LOW),
        Assignment(name="Not due yet, high priority", subject="Math",
                   due_date=TODAY + timedelta(days=1),
                   estimated_hours=1, priority=Priority.HIGH),
    ]
    result = prioritize_assignments(assignments, today=TODAY)
    assert result[0].name == "Overdue, low priority"


def test_same_due_date_higher_priority_wins():
    assignments = [
        Assignment(name="Low priority", subject="Art",
                   due_date=TODAY + timedelta(days=5),
                   estimated_hours=2, priority=Priority.LOW),
        Assignment(name="High priority", subject="Math",
                   due_date=TODAY + timedelta(days=5),
                   estimated_hours=2, priority=Priority.HIGH),
    ]
    result = prioritize_assignments(assignments, today=TODAY)
    assert result[0].name == "High priority"


def test_same_due_date_and_priority_more_hours_wins():
    assignments = [
        Assignment(name="Quick task", subject="Art",
                   due_date=TODAY + timedelta(days=5),
                   estimated_hours=1, priority=Priority.MEDIUM),
        Assignment(name="Long task", subject="Math",
                   due_date=TODAY + timedelta(days=5),
                   estimated_hours=6, priority=Priority.MEDIUM),
    ]
    result = prioritize_assignments(assignments, today=TODAY)
    assert result[0].name == "Long task"


def test_empty_list_returns_empty_list():
    assert prioritize_assignments([], today=TODAY) == []


def test_due_today_treated_as_overdue_urgency():
    assignments = [
        Assignment(name="Due today", subject="Art", due_date=TODAY,
                   estimated_hours=1, priority=Priority.LOW),
        Assignment(name="Due tomorrow", subject="Art", due_date=TODAY + timedelta(days=1),
                   estimated_hours=1, priority=Priority.HIGH),
    ]
    result = prioritize_assignments(assignments, today=TODAY)
    assert result[0].name == "Due today"