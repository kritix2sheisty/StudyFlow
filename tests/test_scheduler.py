"""
tests/test_scheduler.py
Pytest suite for scheduler.prioritize_assignments().

Every promise in the module docstring of scheduler.py is pinned here,
so a weight change that breaks one shows up as a failing test rather
than as a confusing schedule.
"""

from datetime import date, timedelta

import pytest

from models import Assignment, Priority
from scheduler import prioritize_assignments

TODAY = date(2026, 8, 14)


def make(name: str, days_from_today: int, priority: Priority, hours: float,
         completed: bool = False) -> Assignment:
    """Build an assignment due `days_from_today` days after TODAY."""
    return Assignment(
        name=name,
        subject="Test",
        due_date=TODAY + timedelta(days=days_from_today),
        estimated_hours=hours,
        priority=priority,
        completed=completed,
    )


def names(assignments) -> list:
    """Prioritize against TODAY and return just the names, in order."""
    return [a.name for a in prioritize_assignments(assignments, today=TODAY)]


# ---------- Basics ----------

def test_empty_list_returns_empty_list():
    assert prioritize_assignments([], today=TODAY) == []


def test_completed_assignments_are_excluded():
    assignments = [
        make("Done", 0, Priority.HIGH, 1, completed=True),
        make("Not done", 0, Priority.LOW, 1),
    ]
    assert names(assignments) == ["Not done"]


def test_all_completed_returns_empty_list():
    assignments = [
        make("Done A", 1, Priority.HIGH, 1, completed=True),
        make("Done B", -3, Priority.LOW, 5, completed=True),
    ]
    assert names(assignments) == []


def test_input_list_is_not_mutated():
    assignments = [
        make("Later", 5, Priority.LOW, 1),
        make("Sooner", 1, Priority.LOW, 1),
    ]
    original_order = [a.name for a in assignments]
    prioritize_assignments(assignments, today=TODAY)
    assert [a.name for a in assignments] == original_order


def test_today_defaults_to_real_today():
    """With no `today` given, an assignment due yesterday is overdue."""
    yesterday = date.today() - timedelta(days=1)
    next_week = date.today() + timedelta(days=7)
    assignments = [
        Assignment(name="Next week", due_date=next_week, priority=Priority.HIGH),
        Assignment(name="Yesterday", due_date=yesterday, priority=Priority.LOW),
    ]
    assert [a.name for a in prioritize_assignments(assignments)][0] == "Yesterday"


# ---------- Tier 1: overdue and due today always come first ----------

def test_overdue_beats_everything_regardless_of_priority():
    assignments = [
        make("Not due yet, high priority", 1, Priority.HIGH, 1),
        make("Overdue, low priority", -3, Priority.LOW, 1),
    ]
    assert names(assignments)[0] == "Overdue, low priority"


def test_due_today_is_treated_as_overdue():
    assignments = [
        make("Due tomorrow, high priority", 1, Priority.HIGH, 1),
        make("Due today, low priority", 0, Priority.LOW, 1),
    ]
    assert names(assignments)[0] == "Due today, low priority"


def test_all_overdue_items_come_before_all_future_items():
    assignments = [
        make("Future A", 2, Priority.HIGH, 5),
        make("Late A", -1, Priority.LOW, 0),
        make("Future B", 1, Priority.HIGH, 5),
        make("Late B", -10, Priority.LOW, 0),
    ]
    assert set(names(assignments)[:2]) == {"Late A", "Late B"}


def test_overdue_items_ranked_by_priority_not_by_lateness():
    """A week late and a day late are both 'late'; priority decides."""
    assignments = [
        make("Week late, low priority", -7, Priority.LOW, 1),
        make("Day late, high priority", -1, Priority.HIGH, 1),
    ]
    assert names(assignments) == ["Day late, high priority", "Week late, low priority"]


# ---------- Deadlines ----------

def test_earlier_deadline_gets_higher_priority():
    assignments = [
        make("Due in 5 days", 5, Priority.MEDIUM, 2),
        make("Due in 2 days", 2, Priority.MEDIUM, 2),
        make("Due in 10 days", 10, Priority.MEDIUM, 2),
    ]
    assert names(assignments) == ["Due in 2 days", "Due in 5 days", "Due in 10 days"]


@pytest.mark.parametrize("later_priority,later_hours", [
    (Priority.LOW, 1),
    (Priority.HIGH, 1),
    (Priority.HIGH, 10),
    (Priority.HIGH, 40),
])
def test_due_tomorrow_beats_anything_due_later(later_priority, later_hours):
    """Promise 3: nothing due in two or more days outranks tomorrow."""
    assignments = [
        make("Due in 2 days", 2, later_priority, later_hours),
        make("Due tomorrow, low priority, no effort", 1, Priority.LOW, 0),
    ]
    assert names(assignments)[0] == "Due tomorrow, low priority, no effort"


def test_same_due_date_higher_priority_wins():
    assignments = [
        make("Low priority", 5, Priority.LOW, 2),
        make("High priority", 5, Priority.HIGH, 2),
        make("Medium priority", 5, Priority.MEDIUM, 2),
    ]
    assert names(assignments) == ["High priority", "Medium priority", "Low priority"]


def test_same_due_date_priority_beats_size():
    """Promise 4: a huge LOW task never outranks a tiny HIGH task due the same day."""
    assignments = [
        make("Low priority, 20 hours", 5, Priority.LOW, 20),
        make("High priority, 1 hour", 5, Priority.HIGH, 1),
    ]
    assert names(assignments)[0] == "High priority, 1 hour"


def test_same_due_date_and_priority_more_hours_wins():
    assignments = [
        make("Quick task", 5, Priority.MEDIUM, 1),
        make("Long task", 5, Priority.MEDIUM, 6),
    ]
    assert names(assignments)[0] == "Long task"


# ---------- Edge cases ----------

def test_zero_effort_is_handled():
    assignments = [
        make("Zero hours", 3, Priority.MEDIUM, 0),
        make("Two hours", 3, Priority.MEDIUM, 2),
    ]
    assert names(assignments) == ["Two hours", "Zero hours"]


def test_negative_effort_is_treated_as_zero():
    assignments = [
        make("Negative hours", 3, Priority.MEDIUM, -5),
        make("Zero hours", 3, Priority.MEDIUM, 0),
        make("One hour", 3, Priority.MEDIUM, 1),
    ]
    result = names(assignments)
    assert result[0] == "One hour"
    # Negative and zero score identically; the stable sort keeps input order.
    assert result[1:] == ["Negative hours", "Zero hours"]


def test_identical_assignments_are_both_kept_in_original_order():
    assignments = [
        make("Twin 1", 4, Priority.MEDIUM, 2),
        make("Twin 2", 4, Priority.MEDIUM, 2),
    ]
    assert names(assignments) == ["Twin 1", "Twin 2"]


@pytest.mark.parametrize("days_left", [1, 2, 3, 4])
def test_within_four_days_deadline_beats_any_importance_or_size(days_left):
    """Promise 7, near side: up to four days out, the deadline still wins."""
    assignments = [
        make("Due next year, high, 40h", 365, Priority.HIGH, 40),
        make("Due soon, low, 0h", days_left, Priority.LOW, 0),
    ]
    assert names(assignments)[0] == "Due soon, low, 0h"


def test_beyond_five_days_importance_and_size_outweigh_deadline():
    """Promise 7, far side: once both are far away, start the big important one."""
    assignments = [
        make("Worksheet, a month, low, 1h", 30, Priority.LOW, 1),
        make("Project, ten years, high, 5h", 3650, Priority.HIGH, 5),
    ]
    assert names(assignments) == ["Project, ten years, high, 5h", "Worksheet, a month, low, 1h"]


# ---------- Conflicting factors (the philosophy, made concrete) ----------

def test_conflict_small_task_due_tomorrow_beats_big_high_priority_task_due_later():
    """Task A: due tomorrow, LOW, 1h.  Task B: due in 20 days, HIGH, 10h."""
    assignments = [
        make("Task B", 20, Priority.HIGH, 10),
        make("Task A", 1, Priority.LOW, 1),
    ]
    assert names(assignments) == ["Task A", "Task B"]


def test_conflict_huge_assignment_due_in_five_days_does_not_beat_small_due_tomorrow():
    """The original uncapped formula got this wrong: 40h beat tomorrow."""
    assignments = [
        make("Huge project, 5 days, high", 5, Priority.HIGH, 40),
        make("Small task, tomorrow, low", 1, Priority.LOW, 1),
    ]
    assert names(assignments)[0] == "Small task, tomorrow, low"


def test_conflict_important_exam_prep_beats_low_priority_busywork_due_a_day_sooner():
    """Promise 6: with a couple of days of slack, importance and size count."""
    assignments = [
        make("Worksheet, 3 days, low, 1h", 3, Priority.LOW, 1),
        make("Exam prep, 4 days, high, 10h", 4, Priority.HIGH, 10),
    ]
    assert names(assignments)[0] == "Exam prep, 4 days, high, 10h"


def test_conflict_same_priority_sooner_deadline_beats_bigger_task_a_day_later():
    assignments = [
        make("Big, 3 days", 3, Priority.MEDIUM, 10),
        make("Small, 2 days", 2, Priority.MEDIUM, 1),
    ]
    assert names(assignments)[0] == "Small, 2 days"


def test_mixed_bag_full_ordering():
    """One end-to-end ordering covering every tier and tiebreaker."""
    assignments = [
        make("F: 20 days, high, 10h", 20, Priority.HIGH, 10),
        make("C: tomorrow, low, 1h", 1, Priority.LOW, 1),
        make("A: overdue, high, 2h", -2, Priority.HIGH, 2),
        make("E: 5 days, high, 8h", 5, Priority.HIGH, 8),
        make("B: due today, medium, 1h", 0, Priority.MEDIUM, 1),
        make("D: 3 days, medium, 1h", 3, Priority.MEDIUM, 1),
        make("Z: done", -5, Priority.HIGH, 1, completed=True),
    ]
    assert names(assignments) == [
        "A: overdue, high, 2h",
        "B: due today, medium, 1h",
        "C: tomorrow, low, 1h",
        "E: 5 days, high, 8h",
        "D: 3 days, medium, 1h",
        "F: 20 days, high, 10h",
    ]
