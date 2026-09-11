"""
tests/test_plan_view.py
The engine's StudyPlan turned into page data, checked against the
mentor's controlled example so the numbers can be worked by hand.

Study time: Monday, Tuesday, Wednesday 4-6 PM (6 hours).
Assignments: Math 2h due Thursday, Physics 5h due Friday.
Expected: Math takes Monday (due first); Physics takes Tuesday and
Wednesday (4h) and has 1h left over. 6 of 7 hours scheduled = 86%.
"""

from datetime import date, timedelta

import pytest

from models import Assignment, Priority, TimeSlot, Weekday
from StudyFlow import plan_view
from study_plan import generate_study_plan

MONDAY = date(2026, 8, 17)
THURSDAY = MONDAY + timedelta(days=3)
FRIDAY = MONDAY + timedelta(days=4)

SLOTS = [TimeSlot(id=i, weekday=d, start_hour=16, end_hour=18)
         for i, d in enumerate((Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY), start=1)]
MATH = Assignment(id=1, name="Math", subject="Math", due_date=THURSDAY, estimated_hours=2, priority=Priority.MEDIUM)
PHYSICS = Assignment(id=2, name="Physics", subject="Physics", due_date=FRIDAY, estimated_hours=5, priority=Priority.HIGH)


@pytest.fixture
def plan():
    return generate_study_plan([MATH, PHYSICS], SLOTS, today=MONDAY)


def test_days_place_the_work_into_the_saved_study_periods(plan):
    days = plan_view.days_of(plan)
    assert [d.label for d in days] == ["Monday 17 Aug", "Tuesday 18 Aug", "Wednesday 19 Aug"]
    assert [d.iso for d in days] == ["2026-08-17", "2026-08-18", "2026-08-19"]
    assert [(b.time, b.label, b.is_break) for b in days[0].blocks] == [("4 PM–6 PM", "Math", "no")]
    assert [(b.time, b.label) for b in days[1].blocks] == [("4 PM–6 PM", "Physics")]
    assert [(b.time, b.label) for b in days[2].blocks] == [("4 PM–6 PM", "Physics")]


def test_breaks_are_marked_as_breaks():
    """Two short tasks in one slot get a break between them."""
    slots = [TimeSlot(id=1, weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]
    a = Assignment(id=1, name="A", subject="A", due_date=THURSDAY, estimated_hours=1, priority=Priority.HIGH)
    b = Assignment(id=2, name="B", subject="B", due_date=THURSDAY, estimated_hours=0.5)
    day = plan_view.days_of(generate_study_plan([a, b], slots, today=MONDAY))[0]
    assert [(x.label, x.is_break) for x in day.blocks] == [("A", "no"), ("Break", "yes"), ("B", "no")]


def test_today_blocks_use_the_dashboard_row_shape(plan):
    assert plan_view.today_blocks(plan, MONDAY) == [{"time": "4 PM–6 PM", "label": "Math", "is_break": "no"}]
    assert plan_view.today_blocks(plan, THURSDAY) == []


def test_totals_are_the_engines_numbers_as_strings(plan):
    assert plan_view.totals(plan) == {"required": "7.0", "scheduled": "6.0", "unscheduled": "1.0", "completion": "86"}


def test_status_rows_carry_status_percent_and_real_risk(plan):
    rows = plan_view.status_rows(plan, SLOTS, MONDAY)
    by_name = {r.name: r for r in rows}
    math, physics = by_name["Math"], by_name["Physics"]
    assert math.status == "COMPLETE" and math.remaining == "0.0" and math.percent == 100
    assert math.risk == "LOW"                                 # nothing remaining -> infinite ratio -> LOW
    assert math.subject == "Math"
    assert physics.status == "PARTIAL"
    assert (physics.scheduled, physics.required, physics.remaining) == ("4.0", "5.0", "1.0")
    assert physics.percent == 80
    # 6h of study time exists before Friday, but all of it is on the
    # schedule (Math 2h, Physics 4h); nothing is free for the 1h left.
    assert physics.risk == "CRITICAL"
    assert physics.id == "2" and physics.due == "2026-08-21"
    for r in rows:
        assert isinstance(r.percent, int)
        assert all(isinstance(getattr(r, f), str) for f in ("id", "name", "subject", "status", "scheduled",
                                                              "required", "remaining", "risk", "due"))


def test_an_assignment_that_cannot_fit_is_partial_and_critical():
    """Due today, 6 hours, but only today's 2 hours are usable: 4h left, 2h of time -> ratio 0.5."""
    rush = Assignment(id=3, name="Rush", subject="R", due_date=MONDAY, estimated_hours=6)
    plan = generate_study_plan([rush], SLOTS, today=MONDAY)
    row = plan_view.status_rows(plan, SLOTS, MONDAY)[0]
    assert row.status == "PARTIAL" and row.remaining == "4.0" and row.percent == 33
    assert row.risk == "CRITICAL"
    assert plan_view.has_unscheduled(plan)
    assert plan_view.totals(plan)["completion"] == "33"


def test_a_completely_unscheduled_assignment_is_zero_percent():
    """Only a Wednesday slot, but the work is due Tuesday: nothing can be placed."""
    slots = [TimeSlot(id=9, weekday=Weekday.WEDNESDAY, start_hour=16, end_hour=18)]
    essay = Assignment(id=4, name="Essay", subject="English", due_date=MONDAY + timedelta(days=1), estimated_hours=2)
    plan = generate_study_plan([essay], slots, today=MONDAY)
    row = plan_view.status_rows(plan, slots, MONDAY)[0]
    assert row.status == "UNSCHEDULED" and row.percent == 0 and row.scheduled == "0.0"
    assert row.risk == "CRITICAL"                             # no time before Tuesday at all
    assert plan_view.totals(plan)["completion"] == "0"


def test_risk_by_name(plan):
    assert plan_view.risk_by_name(plan_view.status_rows(plan, SLOTS, MONDAY)) == {"Math": "LOW", "Physics": "CRITICAL"}


def test_guard_messages():
    assert "assignments" in plan_view.guard_message([], SLOTS)
    assert "study times" in plan_view.guard_message([MATH], [])
    assert plan_view.guard_message([MATH], SLOTS) == ""
