"""
tests/test_study_plan.py
Pytest suite for the StudyFlow weekly workflow.

generate_study_plan() is an orchestrator, so the tests check two
things: that every part of the StudyPlan equals what the responsible
module produces on its own, and that the parts fit together into the
report a student reads.
"""

from datetime import date, timedelta

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_analyzer import (
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    STATUS_UNSCHEDULED,
    at_risk_assignments,
    completion_percentage,
    total_scheduled_hours,
)
from schedule_builder import build_schedule
from scheduler import prioritize_assignments
from study_plan import StudyPlan, format_study_plan, generate_study_plan

MONDAY = date(2026, 8, 17)  # a known Monday
TUESDAY = MONDAY + timedelta(days=1)
WEDNESDAY = MONDAY + timedelta(days=2)
FRIDAY = MONDAY + timedelta(days=4)


def slot(weekday: Weekday, start_hour: int, end_hour: int) -> TimeSlot:
    return TimeSlot(weekday=weekday, start_hour=start_hour, end_hour=end_hour)


def task(name: str, hours: float, due: date = FRIDAY,
         priority: Priority = Priority.MEDIUM, completed: bool = False) -> Assignment:
    return Assignment(name=name, subject=name, due_date=due, estimated_hours=hours,
                      priority=priority, completed=completed)


def week_example():
    """
    Two 2-hour slots and 7 hours of work: Physics fits, Math is
    partly placed, CS gets nothing, Essay is already done.
    """
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [
        task("CS", 2, due=FRIDAY, priority=Priority.LOW),
        task("Physics", 3, due=TUESDAY, priority=Priority.HIGH),
        task("Math", 2, due=WEDNESDAY, priority=Priority.MEDIUM),
        task("Essay", 4, completed=True),
    ]
    return assignments, slots


# ---------- The orchestrator delegates, it does not decide ----------

def test_plan_carries_the_inputs_and_today():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY)
    assert isinstance(plan, StudyPlan)
    assert plan.today == MONDAY
    assert plan.assignments == assignments


def test_prioritized_matches_the_scheduler():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY)
    assert plan.prioritized == prioritize_assignments(assignments, today=MONDAY)
    assert [a.name for a in plan.prioritized] == ["Physics", "Math", "CS"]


def test_schedule_matches_the_builder():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY)
    assert plan.schedule == build_schedule(assignments, slots, today=MONDAY)


def test_totals_and_completion_match_the_analyzer():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY)
    assert plan.required_hours == 7.0
    assert plan.scheduled_hours == total_scheduled_hours(plan.schedule)
    assert plan.scheduled_hours + plan.unscheduled_hours == plan.required_hours
    assert plan.completion == completion_percentage(plan.schedule, assignments)


def test_analyses_and_at_risk_match_the_analyzer():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY)
    statuses = {row.assignment.name: row.status for row in plan.analyses}
    assert statuses == {"CS": STATUS_UNSCHEDULED, "Physics": STATUS_COMPLETE, "Math": STATUS_PARTIAL}
    assert plan.at_risk == at_risk_assignments(plan.schedule, assignments)
    assert [a.name for a in plan.at_risk] == ["CS", "Math"]


def test_builder_options_pass_through():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY, break_minutes=0, days_ahead=1)
    assert TUESDAY not in plan.schedule.by_date          # only one day ahead
    assert "Break" not in [b.label for b in plan.schedule.by_date[MONDAY]]


def test_max_consecutive_minutes_passes_through_to_the_builder():
    """
    A 3h assignment in a 3h block: 120 / Break / 45 by default (the
    v1.1 two-hour maximum), one chunk when None is asked for, and
    90 / Break / 75 at 90.
    """
    slots = [slot(Weekday.MONDAY, 15, 18)]
    assignments = [task("Long", 3)]
    default = generate_study_plan(assignments, slots, today=MONDAY)
    assert [(b.label, b.end_minute - b.start_minute) for b in default.schedule.by_date[MONDAY]] == [
        ("Long", 120), ("Break", 15), ("Long", 45),
    ]
    assert default.unscheduled_hours == 0.25

    unlimited = generate_study_plan(assignments, slots, today=MONDAY, max_consecutive_minutes=None)
    assert [b.label for b in unlimited.schedule.by_date[MONDAY]] == ["Long"]
    assert unlimited.unscheduled_hours == 0.0

    capped = generate_study_plan(assignments, slots, today=MONDAY, max_consecutive_minutes=90)
    assert [(b.label, b.end_minute - b.start_minute) for b in capped.schedule.by_date[MONDAY]] == [
        ("Long", 90), ("Break", 15), ("Long", 75),
    ]
    assert capped.unscheduled_hours == 0.25
    assert capped.schedule.unscheduled == build_schedule(
        assignments, slots, today=MONDAY, max_consecutive_minutes=90).unscheduled


def test_min_session_minutes_passes_through_to_the_builder():
    """
    Long 60 then a 10-minute task: refused by the default 30-minute
    minimum, placed after a break when no minimum is asked for.
    """
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Long", 1, priority=Priority.HIGH), task("Tiny", 10 / 60)]
    unlimited = generate_study_plan(assignments, slots, today=MONDAY, min_session_minutes=None)
    assert [b.label for b in unlimited.schedule.by_date[MONDAY]] == ["Long", "Break", "Tiny"]
    assert unlimited.unscheduled_hours == 0.0

    strict = generate_study_plan(assignments, slots, today=MONDAY)          # the default, 30
    assert strict.schedule == generate_study_plan(assignments, slots, today=MONDAY, min_session_minutes=30).schedule
    assert [b.label for b in strict.schedule.by_date[MONDAY]] == ["Long"]
    assert strict.unscheduled_hours == 10 / 60
    assert strict.schedule.unscheduled == build_schedule(
        assignments, slots, today=MONDAY, min_session_minutes=30).unscheduled


def test_inputs_are_not_mutated():
    assignments, slots = week_example()
    before = [a.name for a in assignments]
    generate_study_plan(assignments, slots, today=MONDAY)
    assert [a.name for a in assignments] == before


# ---------- Edge cases ----------

def test_empty_plan():
    plan = generate_study_plan([], [], today=MONDAY)
    assert plan.prioritized == []
    assert plan.schedule.by_date == {}
    assert plan.analyses == [] and plan.at_risk == []
    assert (plan.required_hours, plan.scheduled_hours, plan.unscheduled_hours) == (0.0, 0.0, 0.0)
    assert plan.completion == 100.0


def test_no_study_time_puts_everything_at_risk():
    assignments, _ = week_example()
    plan = generate_study_plan(assignments, [], today=MONDAY)
    assert plan.scheduled_hours == 0.0
    assert plan.completion == 0.0
    assert [a.name for a in plan.at_risk] == ["CS", "Physics", "Math"]


def test_today_defaults_to_the_real_date():
    plan = generate_study_plan([], [], today=None)
    assert plan.today == date.today()


# ---------- The report ----------

def test_report_has_every_section_in_order():
    assignments, slots = week_example()
    text = format_study_plan(generate_study_plan(assignments, slots, today=MONDAY))
    positions = [text.index(h) for h in ("STUDYFLOW", "WEEKLY STUDY PLAN", "THIS WEEK",
                                         "PROGRESS", "AT-RISK ASSIGNMENTS")]
    assert positions == sorted(positions)


def test_report_shows_the_timetable_with_uppercase_day_headings():
    assignments, slots = week_example()
    text = format_study_plan(generate_study_plan(assignments, slots, today=MONDAY))
    assert "MONDAY 2026-08-17" in text
    assert "TUESDAY 2026-08-18" in text
    assert "  4 PM–6 PM  Physics" in text


def test_report_shows_the_progress_numbers():
    assignments, slots = week_example()
    plan = generate_study_plan(assignments, slots, today=MONDAY)
    text = format_study_plan(plan)
    assert "Required work:      7.0h" in text
    assert f"Scheduled work:  {plan.scheduled_hours:6.1f}h" in text
    assert f"Unscheduled work:{plan.unscheduled_hours:6.1f}h" in text
    assert f"Completion:      {plan.completion:6.1f}%" in text


def test_report_lists_at_risk_assignments_with_remaining_hours():
    assignments, slots = week_example()
    text = format_study_plan(generate_study_plan(assignments, slots, today=MONDAY))
    tail = text[text.index("AT-RISK ASSIGNMENTS"):]
    assert "CS\n2.0h remaining (due 2026-08-21)" in tail
    assert "Math\n" in tail and "h remaining (due 2026-08-19)" in tail
    assert "Physics" not in tail
    assert "Essay" not in tail


def test_report_when_nothing_is_at_risk():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    text = format_study_plan(generate_study_plan([task("Physics", 1)], slots, today=MONDAY))
    assert "None. Every assignment is fully scheduled." in text


def test_report_when_nothing_is_scheduled():
    text = format_study_plan(generate_study_plan([], [], today=MONDAY))
    assert "Nothing scheduled." in text
    assert "Completion:       100.0%" in text
