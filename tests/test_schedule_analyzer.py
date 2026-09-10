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
    assignment_status,
    at_risk_assignments,
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
# assignment_status: required -> scheduled -> remaining -> status
# =====================================================================

def _status_example():
    """Physics 4/4h, Math 2.5/4h, CS 0/3h, as in the brief."""
    physics, math, cs = task("Physics", 4), task("Math", 4), task("CS", 3)
    result = ScheduleResult(by_date={
        MONDAY: [ScheduledBlock(8 * 60, 12 * 60, "Physics")],
        TUESDAY: [ScheduledBlock(16 * 60, 18 * 60 + 30, "Math")],
    })
    return result, physics, math, cs


def test_status_fully_scheduled_assignment_is_complete():
    result, physics, _, _ = _status_example()
    assert assignment_status(result, physics) == STATUS_COMPLETE


def test_status_partially_scheduled_assignment_is_partial():
    result, _, math, _ = _status_example()
    assert assignment_status(result, math) == STATUS_PARTIAL


def test_status_completely_unscheduled_assignment_is_unscheduled():
    result, _, _, cs = _status_example()
    assert assignment_status(result, cs) == STATUS_UNSCHEDULED


def test_status_zero_hour_assignment_is_complete():
    """No study time is required, so nothing is missing."""
    result, _, _, _ = _status_example()
    assert assignment_status(result, task("Reading", 0)) == STATUS_COMPLETE
    assert assignment_status(ScheduleResult(), task("Reading", 0)) == STATUS_COMPLETE


def test_status_completed_assignment_is_complete_whatever_the_schedule():
    result, _, _, _ = _status_example()
    assert assignment_status(result, task("Handed in", 5, completed=True)) == STATUS_COMPLETE


def test_status_follows_a_real_schedule():
    """Through build_schedule: 3h + 2h + 1h wanted, 4h available."""
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    physics = task("Physics", 3, priority=Priority.HIGH)
    math = task("Math", 2, priority=Priority.MEDIUM)
    cs = task("CS", 1, priority=Priority.LOW)
    result = build_schedule([physics, math, cs], slots, today=MONDAY)
    assert assignment_status(result, physics) == STATUS_COMPLETE
    assert assignment_status(result, math) == STATUS_PARTIAL
    assert assignment_status(result, cs) == STATUS_UNSCHEDULED


def test_status_agrees_with_analyze_assignments():
    result, physics, math, cs = _status_example()
    rows = analyze_assignments(result, [physics, math, cs])
    assert [r.status for r in rows] == [assignment_status(result, a) for a in (physics, math, cs)]


# =====================================================================
# at_risk_assignments: not completed + not fully scheduled
# =====================================================================

def test_partial_assignment_is_at_risk():
    result, _, math, _ = _status_example()          # Math: 2.5 of 4 hours
    assert at_risk_assignments(result, [math]) == [math]


def test_unscheduled_assignment_is_at_risk():
    result, _, _, cs = _status_example()            # CS: 0 of 3 hours
    assert at_risk_assignments(result, [cs]) == [cs]


def test_completed_assignment_is_not_at_risk():
    result, _, _, _ = _status_example()
    done = task("Handed in", 5, completed=True)     # nothing of it is scheduled
    assert at_risk_assignments(result, [done]) == []


def test_fully_scheduled_assignment_is_not_at_risk():
    result, physics, _, _ = _status_example()       # Physics: 4 of 4 hours
    assert at_risk_assignments(result, [physics]) == []


def test_zero_hour_assignment_is_not_at_risk():
    assert at_risk_assignments(ScheduleResult(), [task("Reading", 0)]) == []


def test_fully_scheduled_assignment_due_today_is_not_at_risk():
    """The deadline is today, but every hour is placed today: fine."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    due_today = task("Due today", 2, due=MONDAY)
    result = build_schedule([due_today], slots, today=MONDAY)
    assert assignment_status(result, due_today) == STATUS_COMPLETE
    assert at_risk_assignments(result, [due_today]) == []


def test_overdue_assignment_not_fully_scheduled_is_at_risk():
    """A missed deadline makes the missing hours more urgent, not less."""
    overdue = task("Overdue", 3, due=MONDAY - timedelta(days=2))
    result = build_schedule([overdue], [slot(Weekday.MONDAY, 16, 18)], today=MONDAY)
    assert assignment_status(result, overdue) == STATUS_PARTIAL
    assert at_risk_assignments(result, [overdue]) == [overdue]


def test_at_risk_keeps_order_and_mixes_all_cases():
    """The brief's table in one list, through a real schedule."""
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    physics = task("Physics Lab", 3, priority=Priority.HIGH)
    math = task("Math IA", 2, priority=Priority.MEDIUM)
    cs = task("Computer Science Project", 6, priority=Priority.LOW)
    done = task("Essay", 4, completed=True)
    reading = task("Reading", 0)
    result = build_schedule([physics, math, cs, done, reading], slots, today=MONDAY)
    assert assignment_status(result, physics) == STATUS_COMPLETE
    assert assignment_status(result, math) == STATUS_PARTIAL
    assert assignment_status(result, cs) == STATUS_UNSCHEDULED
    assert at_risk_assignments(result, [physics, math, cs, done, reading]) == [math, cs]


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


# ---------- The analysis report ----------

def _report_example():
    """
    The report from the brief: Mathematics 2/2h complete, Physics
    3/5h partial, Computer Science 0/4h unscheduled. Slots give 4h
    before Physics's Tuesday deadline (ratio 2.0, LOW) and 2h before
    Computer Science's Monday deadline (ratio 0.5, CRITICAL).
    """
    maths = task("Mathematics", 2, due=FRIDAY)
    physics = task("Physics", 5, due=TUESDAY)
    cs = task("Computer Science", 4, due=MONDAY)
    result = ScheduleResult(
        by_date={MONDAY: [ScheduledBlock(9 * 60, 11 * 60, "Mathematics"),
                          ScheduledBlock(16 * 60, 19 * 60, "Physics")]},
        unscheduled=[(physics, 2.0), (cs, 4.0)],
    )
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    return result, [maths, physics, cs], slots


def test_format_analysis_basic_report_has_the_headings_and_totals():
    result, assignments, slots = _report_example()
    text = format_analysis(result, assignments, slots, today=MONDAY)
    for needle in ("STUDYFLOW ANALYSIS", "Required work:", "Scheduled work:",
                   "Unscheduled work:", "Completion:", "ASSIGNMENTS"):
        assert needle in text
    assert "Required work:     11.0h" in text
    assert "Scheduled work:     5.0h" in text
    assert "Unscheduled work:   6.0h" in text
    assert f"Completion:      {5 / 11 * 100:6.1f}%" in text


def test_format_analysis_complete_assignment():
    result, assignments, slots = _report_example()
    text = format_analysis(result, assignments, slots, today=MONDAY)
    assert "Mathematics\n  Status: COMPLETE\n  Scheduled: 2.0h\n" in text
    maths_block = text[text.index("Mathematics"):text.index("Physics")]
    assert "Remaining" not in maths_block and "Risk" not in maths_block


def test_format_analysis_partial_assignment_shows_remaining_hours():
    result, assignments, slots = _report_example()
    text = format_analysis(result, assignments, slots, today=MONDAY)
    assert "Physics\n  Status: PARTIAL\n  Scheduled: 3.0h\n  Remaining: 2.0h\n" in text


def test_format_analysis_at_risk_assignment_shows_its_risk_level():
    result, assignments, slots = _report_example()
    text = format_analysis(result, assignments, slots, today=MONDAY)
    assert "Computer Science\n  Status: UNSCHEDULED\n  Scheduled: 0.0h\n  Remaining: 4.0h\n  Risk: CRITICAL" in text
    assert "Remaining: 2.0h\n  Risk: LOW" in text          # Physics: 4h before Tuesday for 2h left


def test_format_analysis_without_slots_omits_the_risk_line():
    """The brief's two-argument form still works; risk needs the slots."""
    result, assignments, _ = _report_example()
    text = format_analysis(result, assignments)
    assert "Status: UNSCHEDULED" in text
    assert "Remaining: 4.0h" in text
    assert "Risk:" not in text


def test_format_analysis_with_no_assignments_does_not_crash():
    text = format_analysis(ScheduleResult(), [])
    assert "STUDYFLOW ANALYSIS" in text
    assert "Completion:       100.0%" in text
    assert "No active assignments to analyse." in text


def test_format_analysis_skips_completed_assignments():
    result, assignments, slots = _report_example()
    text = format_analysis(result, assignments + [task("Handed in", 3, completed=True)], slots, today=MONDAY)
    assert "Handed in" not in text
    assert "Required work:     11.0h" in text


def test_format_analysis_uses_the_existing_calculations():
    """The report's numbers are the analyzer's numbers, not a second computation."""
    result, assignments, slots = _report_example()
    text = format_analysis(result, assignments, slots, today=MONDAY)
    assert f"{total_scheduled_hours(result):6.1f}h" in text
    assert f"{total_unscheduled_hours(result):6.1f}h" in text
    assert f"{completion_percentage(result, assignments):6.1f}%" in text
    for a in assignments:
        assert f"{a.name}\n  Status: {assignment_status(result, a)}" in text


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
