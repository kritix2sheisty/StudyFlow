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
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    STATUS_UNSCHEDULED,
    analyze_assignments,
    completion_percentage,
    format_analysis,
    format_summary,
    scheduled_hours_for_assignment,
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


# =====================================================================
# scheduled_hours_for_assignment: the building block
# =====================================================================

def _three_day_example():
    """Monday Physics 1.5h, Tuesday Physics 2.0h, Wednesday Math 1.0h."""
    physics, math = task("Physics", 3.5), task("Math", 1)
    result = ScheduleResult(by_date={
        MONDAY: [ScheduledBlock(16 * 60, 17 * 60 + 30, "Physics")],
        TUESDAY: [ScheduledBlock(16 * 60, 18 * 60, "Physics")],
        MONDAY + timedelta(days=2): [ScheduledBlock(16 * 60, 17 * 60, "Math")],
    })
    return result, physics, math


def test_scheduled_hours_for_assignment():
    """The example from the brief: 1.5 + 2.0 = 3.5 for Physics."""
    result, physics, _ = _three_day_example()
    assert scheduled_hours_for_assignment(result, physics) == 3.5


def test_scheduled_hours_completely_scheduled_assignment():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    essay = task("Essay", 2)
    result = build_schedule([essay], slots, today=MONDAY)
    assert scheduled_hours_for_assignment(result, essay) == 2.0


def test_scheduled_hours_split_across_multiple_blocks():
    """Two slots on Monday and one on Tuesday, all partly used by one task."""
    slots = [slot(Weekday.MONDAY, 8, 9), slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 17)]
    project = task("Project", 3.75)
    result = build_schedule([project], slots, today=MONDAY)
    assert scheduled_hours_for_assignment(result, project) == 3.75


def test_scheduled_hours_with_no_scheduled_time_is_zero():
    result, physics, _ = _three_day_example()
    cs = task("CS", 4)
    assert scheduled_hours_for_assignment(result, cs) == 0.0
    # Also when the schedule is empty altogether.
    assert scheduled_hours_for_assignment(ScheduleResult(), physics) == 0.0


def test_scheduled_hours_does_not_count_breaks():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    first, second = task("First", 1, priority=Priority.HIGH), task("Second", 1)
    result = build_schedule([first, second], slots, today=MONDAY, break_minutes=15)
    assert [b.label for b in result.by_date[MONDAY]] == ["First", "Break", "Second"]
    assert scheduled_hours_for_assignment(result, first) == 1.0
    assert scheduled_hours_for_assignment(result, second) == 0.75
    # Even an assignment literally named "Break" gets no credit for breaks.
    assert scheduled_hours_for_assignment(result, task("Break", 1)) == 0.0


def test_scheduled_hours_does_not_count_other_assignments():
    result, physics, math = _three_day_example()
    assert scheduled_hours_for_assignment(result, math) == 1.0
    assert scheduled_hours_for_assignment(result, physics) == 3.5
    # A different assignment with a similar name is still a different assignment.
    assert scheduled_hours_for_assignment(result, task("Physics Lab", 1)) == 0.0


# =====================================================================
# Assignment-level analysis (Phase 3.4)
# =====================================================================

def _brief_example():
    """
    The table from the Phase 3.4 brief: Physics Lab 100%, Math
    Homework 50%, Computer Science 0%, English Essay 100%.
    """
    assignments = [
        task("Physics Lab", 2),
        task("Math Homework", 2),
        task("Computer Science", 3),
        task("English Essay", 1),
    ]
    result = ScheduleResult(
        by_date={
            MONDAY: [ScheduledBlock(16 * 60, 18 * 60, "Physics Lab")],
            TUESDAY: [ScheduledBlock(16 * 60, 17 * 60, "Math Homework"),
                      ScheduledBlock(17 * 60, 17 * 60 + 15, "Break"),
                      ScheduledBlock(17 * 60 + 15, 18 * 60 + 15, "English Essay")],
        },
        unscheduled=[(assignments[1], 1.0), (assignments[2], 3.0)],
    )
    return result, assignments


def test_analysis_matches_the_brief_example():
    result, assignments = _brief_example()
    rows = analyze_assignments(result, assignments)
    assert [(r.assignment.name, r.percent_scheduled, r.status) for r in rows] == [
        ("Physics Lab", 100.0, STATUS_COMPLETE),
        ("Math Homework", 50.0, STATUS_PARTIAL),
        ("Computer Science", 0.0, STATUS_UNSCHEDULED),
        ("English Essay", 100.0, STATUS_COMPLETE),
    ]


def test_analysis_hours_follow_the_chain_from_blocks_to_remaining():
    """Assignment -> blocks -> scheduled hours -> remaining hours."""
    result, assignments = _brief_example()
    math = analyze_assignments(result, assignments)[1]
    assert math.required_hours == 2.0
    assert math.scheduled_hours == 1.0
    assert math.remaining_hours == 1.0


def test_analysis_remaining_agrees_with_the_builder():
    """The hours derived from blocks match what the builder reported."""
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Physics", 3, priority=Priority.HIGH), task("Math", 2), task("CS", 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    reported = {a.name: hours for a, hours in result.unscheduled}
    for row in analyze_assignments(result, assignments):
        assert row.remaining_hours == pytest.approx(reported.get(row.assignment.name, 0.0))


def test_analysis_sums_an_assignment_split_across_days():
    slots = [slot(Weekday.MONDAY, 16, 17), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Big project", 2.5)]
    result = build_schedule(assignments, slots, today=MONDAY)
    row = analyze_assignments(result, assignments)[0]
    assert row.scheduled_hours == 2.5
    assert row.status == STATUS_COMPLETE


def test_analysis_keeps_the_order_given():
    result, assignments = _brief_example()
    names = [r.assignment.name for r in analyze_assignments(result, reversed(assignments))]
    assert names == ["English Essay", "Computer Science", "Math Homework", "Physics Lab"]


def test_analysis_skips_completed_and_treats_zero_hours_as_complete():
    assignments = [task("Done", 4, completed=True), task("Nothing to do", 0), task("Physics", 1)]
    result = build_schedule(assignments, [slot(Weekday.MONDAY, 16, 18)], today=MONDAY)
    rows = analyze_assignments(result, assignments)
    assert [r.assignment.name for r in rows] == ["Nothing to do", "Physics"]
    assert rows[0].status == STATUS_COMPLETE
    assert rows[0].percent_scheduled == 100.0


def test_format_analysis_renders_the_table():
    result, assignments = _brief_example()
    text = format_analysis(analyze_assignments(result, assignments))
    lines = text.splitlines()
    assert lines[0] == "StudyFlow Schedule Analysis"
    assert lines[2] == "Physics Lab       100% scheduled   COMPLETE"
    assert lines[3] == "Math Homework      50% scheduled   PARTIAL"
    assert lines[4] == "Computer Science    0% scheduled   UNSCHEDULED"
    assert lines[5] == "English Essay     100% scheduled   COMPLETE"


def test_format_analysis_with_nothing_active():
    assert format_analysis([]) == "No active assignments to analyse."


def test_format_summary_renders_the_totals():
    result, assignments = _brief_example()
    text = format_summary(result, assignments)
    assert text.splitlines() == [
        "Schedule Summary",
        "Required:       8.0h",
        "Scheduled:      4.0h",
        "Unscheduled:    4.0h",
        "Completion:    50.0%",
    ]
