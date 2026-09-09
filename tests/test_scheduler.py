"""
tests/test_scheduler.py
Pytest suite for scheduler.prioritize_assignments().

Part 1 is the 13 scenarios from the Phase 2 write-up, one test each,
numbered to match. Where a scenario asked an open question ("do they
tie?", "what decides the order?"), the docstring gives the answer the
current design settles on, and the assertion pins it.

Part 2 pins the promises in the scheduler.py module docstring that the
13 scenarios don't already cover, so a weight change that breaks one
shows up as a failing test rather than as a confusing schedule.
"""

from datetime import date, timedelta

import pytest

from models import Assignment, Priority
from scheduler import prioritize_assignments

TODAY = date(2026, 8, 14)


def make(name: str, days_from_today: int, priority: Priority, hours: float,
         completed: bool = False, subject: str = "Test") -> Assignment:
    """Build an assignment due `days_from_today` days after TODAY."""
    return Assignment(
        name=name,
        subject=subject,
        due_date=TODAY + timedelta(days=days_from_today),
        estimated_hours=hours,
        priority=priority,
        completed=completed,
    )


def names(assignments) -> list:
    """Prioritize against TODAY and return just the names, in order."""
    return [a.name for a in prioritize_assignments(assignments, today=TODAY)]


# =====================================================================
# Part 1 — the 13 scenarios
# =====================================================================

# ---------- Basic ----------

def test_01_one_assignment():
    assignments = [make("Solo task", 3, Priority.MEDIUM, 2, subject="Math")]
    assert names(assignments) == ["Solo task"]


def test_02_several_assignments_different_deadlines():
    """Priority and effort held equal: expect pure due-date ordering."""
    assignments = [
        make("Due in 10 days", 10, Priority.MEDIUM, 2, subject="Math"),
        make("Due in 1 day", 1, Priority.MEDIUM, 2, subject="Math"),
        make("Due in 5 days", 5, Priority.MEDIUM, 2, subject="Math"),
    ]
    assert names(assignments) == ["Due in 1 day", "Due in 5 days", "Due in 10 days"]


# ---------- Edge cases ----------

def test_03_completed_assignment_mixed_with_active_ones():
    """Only the active one should appear at all."""
    assignments = [
        make("Completed but due tomorrow", 1, Priority.HIGH, 1, completed=True, subject="Bio"),
        make("Active, due in 5 days", 5, Priority.LOW, 1, subject="Bio"),
    ]
    assert names(assignments) == ["Active, due in 5 days"]


def test_04_due_exactly_today():
    """'Due today' wins despite lower priority: it is in the overdue tier."""
    assignments = [
        make("Due today", 0, Priority.MEDIUM, 2, subject="CS"),
        make("Due in 3 days", 3, Priority.HIGH, 2, subject="CS"),
    ]
    assert names(assignments) == ["Due today", "Due in 3 days"]


def test_05_overdue_by_different_amounts():
    """
    Answer to 'does more overdue rank higher?': no, they tie.

    How late something is does not matter. A day late and ten days
    late are both 'late; do it now', so with priority and effort equal
    they score identically and the stable sort keeps input order.
    """
    assignments = [
        make("Overdue by 1 day", -1, Priority.MEDIUM, 2, subject="Art"),
        make("Overdue by 10 days", -10, Priority.MEDIUM, 2, subject="Art"),
    ]
    assert names(assignments) == ["Overdue by 1 day", "Overdue by 10 days"]
    # Input order is the only thing separating them: flip it, order flips.
    assert names(list(reversed(assignments))) == ["Overdue by 10 days", "Overdue by 1 day"]


def test_06_same_deadline_different_priority():
    assignments = [
        make("Same date, LOW", 4, Priority.LOW, 2, subject="Art"),
        make("Same date, HIGH", 4, Priority.HIGH, 2, subject="Art"),
    ]
    assert names(assignments) == ["Same date, HIGH", "Same date, LOW"]


def test_07_same_priority_different_deadlines():
    assignments = [
        make("MEDIUM, due in 8 days", 8, Priority.MEDIUM, 2, subject="Art"),
        make("MEDIUM, due in 2 days", 2, Priority.MEDIUM, 2, subject="Art"),
    ]
    assert names(assignments) == ["MEDIUM, due in 2 days", "MEDIUM, due in 8 days"]


def test_08_zero_and_near_zero_estimated_effort():
    """A 0-hour estimate does not crash anything; it just ranks lowest."""
    assignments = [
        make("Zero-hour task", 3, Priority.MEDIUM, 0, subject="Art"),
        make("0.1-hour task", 3, Priority.MEDIUM, 0.1, subject="Art"),
        make("Normal 3-hour task", 3, Priority.MEDIUM, 3, subject="Art"),
    ]
    assert names(assignments) == ["Normal 3-hour task", "0.1-hour task", "Zero-hour task"]


# ---------- Interesting / adversarial ----------

def test_09_high_priority_far_away_vs_low_priority_due_tomorrow():
    """Urgency wins. Nothing due later can outrank something due tomorrow."""
    assignments = [
        make("HIGH, due in 25 days", 25, Priority.HIGH, 3, subject="Math"),
        make("LOW, due tomorrow", 1, Priority.LOW, 1, subject="Art"),
    ]
    assert names(assignments) == ["LOW, due tomorrow", "HIGH, due in 25 days"]


def test_10_huge_assignment_due_soon_vs_small_assignments_due_soon():
    """
    Answer to 'can raw effort hours outweigh a closer due date?': no.

    Effort is capped, so the 20-hour task cannot jump the 2-day
    deadline. It does go ahead of the 1-hour task with the same
    3-day deadline, because a big task needs starting sooner.
    """
    assignments = [
        make("HUGE, 20h, due in 3 days", 3, Priority.MEDIUM, 20, subject="CS"),
        make("Small, 1h, due in 3 days", 3, Priority.MEDIUM, 1, subject="CS"),
        make("Small, 1h, due in 2 days", 2, Priority.MEDIUM, 1, subject="CS"),
    ]
    assert names(assignments) == [
        "Small, 1h, due in 2 days",
        "HUGE, 20h, due in 3 days",
        "Small, 1h, due in 3 days",
    ]


def test_11_several_assignments_competing_for_the_same_deadline():
    """4-way tie-break: priority first, then effort, with no ties."""
    assignments = [
        make("Same day, LOW, 1h", 4, Priority.LOW, 1, subject="A"),
        make("Same day, HIGH, 1h", 4, Priority.HIGH, 1, subject="B"),
        make("Same day, HIGH, 8h", 4, Priority.HIGH, 8, subject="C"),
        make("Same day, MEDIUM, 4h", 4, Priority.MEDIUM, 4, subject="D"),
    ]
    assert names(assignments) == [
        "Same day, HIGH, 8h",
        "Same day, HIGH, 1h",
        "Same day, MEDIUM, 4h",
        "Same day, LOW, 1h",
    ]


def test_12_perfect_tie_identical_due_date_priority_and_effort():
    """
    Answer to 'what decides the order?': the order they were given in.

    The sort is stable, so three clones come back exactly as entered.
    Nothing else (name, subject, id) is ever consulted.
    """
    assignments = [
        make("Clone A", 5, Priority.MEDIUM, 2, subject="X"),
        make("Clone B", 5, Priority.MEDIUM, 2, subject="Y"),
        make("Clone C", 5, Priority.MEDIUM, 2, subject="Z"),
    ]
    assert names(assignments) == ["Clone A", "Clone B", "Clone C"]


def test_13_empty_input():
    assert prioritize_assignments([], today=TODAY) == []


# =====================================================================
# Part 2 — the remaining promises from scheduler.py
# =====================================================================

# ---------- Plumbing ----------

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


# ---------- Promise 2: the overdue tier ----------

def test_all_overdue_items_come_before_all_future_items():
    assignments = [
        make("Future A", 2, Priority.HIGH, 5),
        make("Late A", -1, Priority.LOW, 0),
        make("Future B", 1, Priority.HIGH, 5),
        make("Late B", -10, Priority.LOW, 0),
    ]
    assert set(names(assignments)[:2]) == {"Late A", "Late B"}


def test_overdue_items_ranked_by_priority_not_by_lateness():
    assignments = [
        make("Week late, low priority", -7, Priority.LOW, 1),
        make("Day late, high priority", -1, Priority.HIGH, 1),
    ]
    assert names(assignments) == ["Day late, high priority", "Week late, low priority"]


# ---------- Promise 3: tomorrow beats everything later ----------

@pytest.mark.parametrize("later_priority,later_hours", [
    (Priority.LOW, 1),
    (Priority.HIGH, 1),
    (Priority.HIGH, 10),
    (Priority.HIGH, 40),
])
def test_due_tomorrow_beats_anything_due_later(later_priority, later_hours):
    assignments = [
        make("Due in 2 days", 2, later_priority, later_hours),
        make("Due tomorrow, low priority, no effort", 1, Priority.LOW, 0),
    ]
    assert names(assignments)[0] == "Due tomorrow, low priority, no effort"


# ---------- Promise 4: same date, priority beats size, every pair ----------

@pytest.mark.parametrize("lower,higher", [
    (Priority.LOW, Priority.MEDIUM),
    (Priority.MEDIUM, Priority.HIGH),
    (Priority.LOW, Priority.HIGH),
])
def test_same_due_date_priority_beats_size_for_every_priority_pair(lower, higher):
    """Scenario 11 found the MEDIUM/HIGH gap; this pins all three gaps."""
    assignments = [
        make("Lower priority, 40 hours", 5, lower, 40),
        make("Higher priority, 0 hours", 5, higher, 0),
    ]
    assert names(assignments)[0] == "Higher priority, 0 hours"


# ---------- Promise 5: same date and priority, bigger first ----------

def test_same_due_date_and_priority_more_hours_wins():
    assignments = [
        make("Quick task", 5, Priority.MEDIUM, 1),
        make("Long task", 5, Priority.MEDIUM, 6),
    ]
    assert names(assignments)[0] == "Long task"


# ---------- Promises 6 and 7: how far a deadline reaches ----------

def test_important_exam_prep_beats_low_priority_busywork_due_a_day_sooner():
    """Promise 6: with a couple of days of slack, importance and size count."""
    assignments = [
        make("Worksheet, 3 days, low, 1h", 3, Priority.LOW, 1),
        make("Exam prep, 4 days, high, 10h", 4, Priority.HIGH, 10),
    ]
    assert names(assignments)[0] == "Exam prep, 4 days, high, 10h"


def test_same_priority_sooner_deadline_beats_bigger_task_a_day_later():
    assignments = [
        make("Big, 3 days", 3, Priority.MEDIUM, 10),
        make("Small, 2 days", 2, Priority.MEDIUM, 1),
    ]
    assert names(assignments)[0] == "Small, 2 days"


@pytest.mark.parametrize("days_left", [1, 2, 3, 4, 5])
def test_within_five_days_deadline_beats_any_importance_or_size(days_left):
    """Promise 7, near side: up to five days out, the deadline still wins."""
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


# ---------- Everything at once ----------

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
        "D: 3 days, medium, 1h",
        "E: 5 days, high, 8h",
        "F: 20 days, high, 10h",
    ]
