"""
tests/test_schedule_analyzer.py
Pytest suite for schedule_analyzer: measuring a finished schedule.

Most cases build a real schedule with build_schedule() so the numbers
come from the same path the app uses. One case hand-builds a
ScheduleResult to pin the exact worked example from the Phase 3.3
brief without depending on how the builder would lay it out.
"""

from datetime import date, timedelta

import pytest

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_analyzer import (
    completion_percentage,
    total_required_hours,
    total_scheduled_hours,
    total_unscheduled_hours,
)
from schedule_builder import ScheduledBlock, ScheduleResult, build_schedule

MONDAY = date(2026, 8, 17)  # a known Monday
TUESDAY = MONDAY + timedelta(days=1)
FRIDAY = MONDAY + timedelta(days=4)


def slot(weekday: Weekday, start_hour: int, end_hour: int) -> TimeSlot:
    return TimeSlot(weekday=weekday, start_hour=start_hour, end_hour=end_hour)


def task(name: str, hours: float, due: date = FRIDAY,
         priority: Priority = Priority.MEDIUM, completed: bool = False) -> Assignment:
    return Assignment(name=name, subject=name, due_date=due, estimated_hours=hours,
                      priority=priority, completed=completed)


# ---------- The worked example from the brief ----------

def test_worked_example_from_the_brief():
    """
    Physics 3h, Math 2h, CS 1h scheduled; Physics 1h and CS 2h
    unscheduled. Scheduled = 6, unscheduled = 3.
    """
    physics, cs = task("Physics", 4), task("CS", 3)
    result = ScheduleResult(
        by_date={
            MONDAY: [ScheduledBlock(16 * 60, 19 * 60, "Physics")],
            TUESDAY: [ScheduledBlock(16 * 60, 18 * 60, "Math"),
                      ScheduledBlock(18 * 60, 18 * 60 + 15, "Break"),
                      ScheduledBlock(18 * 60 + 15, 19 * 60 + 15, "CS")],
        },
        unscheduled=[(physics, 1.0), (cs, 2.0)],
    )
    assert total_scheduled_hours(result) == 6.0
    assert total_unscheduled_hours(result) == 3.0


def test_nine_of_twelve_hours_is_seventy_five_percent():
    """9 scheduled / 12 required * 100 = 75.0, as in the brief."""
    assignments = [task("Physics", 6), task("Math", 6)]
    result = ScheduleResult(
        by_date={MONDAY: [ScheduledBlock(8 * 60, 17 * 60, "Physics")]},   # 9 hours
        unscheduled=[(assignments[1], 3.0)],
    )
    assert completion_percentage(result, assignments) == 75.0


# ---------- 1. No assignments ----------

def test_no_assignments():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    result = build_schedule([], slots, today=MONDAY)
    assert total_scheduled_hours(result) == 0.0
    assert total_unscheduled_hours(result) == 0.0
    # No unfinished work, so the schedule is complete.
    assert completion_percentage(result, []) == 100.0


# ---------- 2. Everything scheduled ----------

def test_everything_scheduled():
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Physics", 2), task("Math", 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert total_scheduled_hours(result) == 3.0
    assert total_unscheduled_hours(result) == 0.0
    assert completion_percentage(result, assignments) == 100.0


# ---------- 3. Some work unscheduled ----------

def test_some_work_unscheduled():
    """4 hours free, 6 required: 4 scheduled, 2 unscheduled, 66.7%."""
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Physics", 4, priority=Priority.HIGH), task("Math", 2)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert total_scheduled_hours(result) == 4.0
    assert total_unscheduled_hours(result) == 2.0
    assert completion_percentage(result, assignments) == pytest.approx(66.667, abs=0.001)


def test_scheduled_plus_unscheduled_equals_required():
    """Nothing is lost or invented on the way through the builder."""
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.WEDNESDAY, 9, 12)]
    assignments = [task("A", 3.5, priority=Priority.HIGH), task("B", 2), task("C", 1.25)]
    result = build_schedule(assignments, slots, today=MONDAY)
    total = total_scheduled_hours(result) + total_unscheduled_hours(result)
    assert total == pytest.approx(total_required_hours(assignments))


# ---------- 4. Everything unscheduled ----------

def test_everything_unscheduled_with_no_study_time():
    assignments = [task("Physics", 2), task("Math", 3)]
    result = build_schedule(assignments, [], today=MONDAY)
    assert total_scheduled_hours(result) == 0.0
    assert total_unscheduled_hours(result) == 5.0
    assert completion_percentage(result, assignments) == 0.0


def test_everything_unscheduled_because_the_only_slot_is_after_the_deadline():
    slots = [slot(Weekday.WEDNESDAY, 16, 18)]
    assignments = [task("Due Tuesday", 2, due=TUESDAY)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert total_scheduled_hours(result) == 0.0
    assert total_unscheduled_hours(result) == 2.0
    assert completion_percentage(result, assignments) == 0.0


# ---------- 5. Decimal-hour assignments ----------

def test_decimal_hours():
    """1.5h + 0.75h in a 2h slot: 1.5 + break + 0.25 placed, 0.5 flagged."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Physics", 1.5, priority=Priority.HIGH), task("Math", 0.75)]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=15)
    assert total_scheduled_hours(result) == 1.75
    assert total_unscheduled_hours(result) == 0.5
    assert total_required_hours(assignments) == 2.25
    assert completion_percentage(result, assignments) == pytest.approx(77.778, abs=0.001)


# ---------- Rules the numbers depend on ----------

def test_breaks_are_not_counted_as_scheduled_work():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Physics", 1, priority=Priority.HIGH), task("Math", 0.5)]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=15)
    labels = [b.label for b in result.by_date[MONDAY]]
    assert "Break" in labels
    assert total_scheduled_hours(result) == 1.5


def test_completed_assignments_are_not_required_work():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Physics", 2), task("Done already", 10, completed=True)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert total_required_hours(assignments) == 2.0
    assert completion_percentage(result, assignments) == 100.0


def test_only_completed_or_zero_hour_assignments_count_as_complete():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Done", 3, completed=True), task("Nothing to do", 0)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert total_required_hours(assignments) == 0.0
    assert completion_percentage(result, assignments) == 100.0


def test_negative_estimate_counts_as_zero_required():
    assignments = [task("Odd estimate", -3), task("Physics", 2)]
    assert total_required_hours(assignments) == 2.0
