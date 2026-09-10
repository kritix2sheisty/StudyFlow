"""
tests/test_schedule_optimizer.py
Pytest suite for schedule_optimizer.

Phase 4 starts with available_hours_before_deadline(): how much study
time exists between today and an assignment's due date. The first
four tests are the ones from the brief; the rest pin the edges.
"""

import math
from datetime import date, timedelta

import pytest

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_builder import ScheduledBlock, ScheduleResult, build_schedule
from schedule_optimizer import (
    RISK_CRITICAL,
    RISK_HIGH,
    RISK_LOW,
    RISK_MODERATE,
    available_hours_before_deadline,
    deadline_risk_ratio,
    risk_level,
)

MONDAY = date(2026, 8, 17)  # a known Monday
TUESDAY = MONDAY + timedelta(days=1)
WEDNESDAY = MONDAY + timedelta(days=2)
THURSDAY = MONDAY + timedelta(days=3)
FRIDAY = MONDAY + timedelta(days=4)


def slot(weekday: Weekday, start_hour: int, end_hour: int) -> TimeSlot:
    return TimeSlot(weekday=weekday, start_hour=start_hour, end_hour=end_hour)


def task(name: str, due: date, hours: float) -> Assignment:
    return Assignment(name=name, subject=name, due_date=due, estimated_hours=hours,
                      priority=Priority.MEDIUM)


def week(**hours_by_day: int) -> list:
    """week(monday=2, tuesday=3) -> one afternoon slot per named day."""
    return [slot(Weekday.from_name(day), 16, 16 + h) for day, h in hours_by_day.items()]


# ---------- The brief's example ----------

def test_brief_example_monday_to_thursday_is_eight_hours():
    """Mon 2h, Tue 3h, Wed 1h, Thu 2h, Fri 3h; due Thursday -> 8, not 11."""
    slots = week(monday=2, tuesday=3, wednesday=1, thursday=2, friday=3)
    assert available_hours_before_deadline(task("Essay", THURSDAY, 3), slots, MONDAY) == 8.0


# ---------- Test 1 to 4 from the brief ----------

def test_1_plenty_of_time():
    """Required 3h, available 8h -> 8h. The function reports capacity, not need."""
    slots = week(monday=2, tuesday=3, wednesday=1, thursday=2, friday=3)
    assert available_hours_before_deadline(task("Essay", THURSDAY, 3), slots, MONDAY) == 8.0


def test_2_exactly_enough_time():
    """Required 4h, available 4h -> 4h."""
    slots = week(monday=2, tuesday=2)
    assert available_hours_before_deadline(task("Lab", TUESDAY, 4), slots, MONDAY) == 4.0


def test_3_not_enough_time():
    """Required 6h, available 3h -> 3h. Still just the capacity; the shortfall is the next layer's job."""
    slots = week(monday=1, tuesday=2)
    assert available_hours_before_deadline(task("Project", TUESDAY, 6), slots, MONDAY) == 3.0


def test_4_ignores_time_after_the_deadline():
    """Due Wednesday; Mon 2h, Tue 2h, Wed 2h, Thu 5h -> 6h, not 11h."""
    slots = week(monday=2, tuesday=2, wednesday=2, thursday=5)
    assert available_hours_before_deadline(task("Quiz prep", WEDNESDAY, 4), slots, MONDAY) == 6.0


# ---------- Edges ----------

def test_due_date_itself_counts():
    """Same rule as the scheduler: a slot on the due date is usable."""
    slots = week(wednesday=2)
    assert available_hours_before_deadline(task("Due Wednesday", WEDNESDAY, 1), slots, MONDAY) == 2.0


def test_due_today_counts_only_today():
    slots = week(monday=2, tuesday=3)
    assert available_hours_before_deadline(task("Due today", MONDAY, 1), slots, MONDAY) == 2.0


def test_overdue_assignment_has_no_time_left():
    slots = week(monday=2, tuesday=3)
    assert available_hours_before_deadline(task("Was due Friday", MONDAY - timedelta(days=3), 1), slots, MONDAY) == 0.0


def test_no_study_time_at_all():
    assert available_hours_before_deadline(task("Anything", FRIDAY, 2), [], MONDAY) == 0.0


def test_no_study_time_before_the_deadline():
    """Only Friday is free, but the work is due Wednesday."""
    slots = week(friday=3)
    assert available_hours_before_deadline(task("Due Wednesday", WEDNESDAY, 2), slots, MONDAY) == 0.0


def test_several_slots_on_one_day_all_count():
    slots = [slot(Weekday.MONDAY, 8, 9), slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 17)]
    assert available_hours_before_deadline(task("Due Tuesday", TUESDAY, 2), slots, MONDAY) == 4.0


def test_weekly_slots_repeat_when_the_deadline_is_more_than_a_week_away():
    """Due in ten days: next Monday and next Tuesday count again."""
    slots = week(monday=2, tuesday=1)
    ten_days = MONDAY + timedelta(days=10)          # the Thursday after next
    assert available_hours_before_deadline(task("Big project", ten_days, 10), slots, MONDAY) == 6.0


def test_today_can_be_any_weekday():
    """Start on a Wednesday: only Wednesday to Friday count, not the earlier days."""
    slots = week(monday=2, tuesday=2, wednesday=1, thursday=1, friday=1)
    assert available_hours_before_deadline(task("Due Friday", FRIDAY, 2), slots, WEDNESDAY) == 3.0


# =====================================================================
# deadline_risk_ratio: available hours / remaining hours
# =====================================================================

def scheduled(assignment: Assignment, hours: float, day: date = MONDAY) -> ScheduleResult:
    """A schedule with `hours` of this assignment placed on `day`."""
    start = 16 * 60
    return ScheduleResult(by_date={day: [ScheduledBlock(start, start + round(hours * 60), assignment.name)]})


def test_ratio_0_5_is_a_critical_situation():
    """Remaining 4h (6 required, 2 scheduled); available 2h -> 0.5."""
    physics = task("Physics", MONDAY, 6)
    assert deadline_risk_ratio(physics, scheduled(physics, 2), week(monday=2), MONDAY) == 0.5


def test_ratio_1_0_is_exactly_enough_time():
    """Remaining 4h; available 4h (Mon 2, Tue 2, due Tuesday) -> 1.0."""
    physics = task("Physics", TUESDAY, 6)
    assert deadline_risk_ratio(physics, scheduled(physics, 2), week(monday=2, tuesday=2), MONDAY) == 1.0


def test_ratio_1_5_is_the_moderate_boundary():
    """The brief's second example: remaining 4h, available 6h -> 1.5."""
    physics = task("Physics", WEDNESDAY, 6)
    slots = week(monday=2, tuesday=2, wednesday=2)
    assert deadline_risk_ratio(physics, scheduled(physics, 2), slots, MONDAY) == 1.5


def test_ratio_2_0_is_the_low_boundary():
    """Remaining 4h; available 8h (2h a day, Monday to Thursday) -> 2.0."""
    physics = task("Physics", THURSDAY, 6)
    slots = week(monday=2, tuesday=2, wednesday=2, thursday=2)
    assert deadline_risk_ratio(physics, scheduled(physics, 2), slots, MONDAY) == 2.0


def test_ratio_3_0_is_plenty_of_time():
    """Remaining 2h (4 required, 2 scheduled); available 6h -> 3.0."""
    essay = task("Essay", WEDNESDAY, 4)
    slots = week(monday=2, tuesday=2, wednesday=2)
    assert deadline_risk_ratio(essay, scheduled(essay, 2), slots, MONDAY) == 3.0


def test_ratio_for_completed_assignment_is_infinite():
    done = Assignment(name="Done", subject="Done", due_date=TUESDAY, estimated_hours=5, completed=True)
    assert deadline_risk_ratio(done, ScheduleResult(), week(monday=2), MONDAY) == math.inf


def test_ratio_for_zero_hour_assignment_is_infinite():
    reading = task("Reading", TUESDAY, 0)
    assert deadline_risk_ratio(reading, ScheduleResult(), week(monday=2), MONDAY) == math.inf


def test_ratio_with_no_remaining_work_is_infinite():
    """Fully scheduled: nothing left to find time for."""
    physics = task("Physics", TUESDAY, 2)
    assert deadline_risk_ratio(physics, scheduled(physics, 2), week(monday=2), MONDAY) == math.inf


def test_ratio_for_overdue_work_is_zero():
    """Work left and no time before a deadline that has passed."""
    late = task("Late", MONDAY - timedelta(days=1), 3)
    assert deadline_risk_ratio(late, ScheduleResult(), week(monday=2, tuesday=2), MONDAY) == 0.0


def test_ratio_with_no_study_time_is_zero():
    assert deadline_risk_ratio(task("Anything", FRIDAY, 3), ScheduleResult(), [], MONDAY) == 0.0


def test_ratio_uses_the_real_schedule():
    """
    Through build_schedule: two 2-hour slots, Physics 3h due Tuesday
    and Math 3h due Wednesday. Physics fits (infinite); Math gets 45
    minutes after a break, leaving 2.25h against 4h of capacity
    before Wednesday.
    """
    slots = week(monday=2, tuesday=2)
    physics = task("Physics", TUESDAY, 3)
    math_hw = task("Math", WEDNESDAY, 3)
    result = build_schedule([physics, math_hw], slots, today=MONDAY)
    assert deadline_risk_ratio(physics, result, slots, MONDAY) == math.inf
    assert deadline_risk_ratio(math_hw, result, slots, MONDAY) == pytest.approx(4 / 2.25)


# =====================================================================
# risk_level: ratio -> CRITICAL / HIGH / MODERATE / LOW
# =====================================================================

@pytest.mark.parametrize("ratio,level", [
    (0.5, RISK_CRITICAL),
    (1.0, RISK_HIGH),
    (1.4, RISK_HIGH),
    (1.5, RISK_MODERATE),
    (1.9, RISK_MODERATE),
    (2.0, RISK_LOW),
    (3.0, RISK_LOW),
])
def test_risk_level_examples_from_the_brief(ratio, level):
    assert risk_level(ratio) == level


@pytest.mark.parametrize("ratio,level", [
    (0.99, RISK_CRITICAL),   # just under: still less time than work
    (1.0, RISK_HIGH),        # the boundary belongs to the safer side
    (1.49, RISK_HIGH),
    (1.5, RISK_MODERATE),
    (1.99, RISK_MODERATE),
    (2.0, RISK_LOW),
])
def test_risk_level_boundaries(ratio, level):
    assert risk_level(ratio) == level


def test_risk_level_zero_is_critical():
    assert risk_level(0) == RISK_CRITICAL
    assert risk_level(0.0) == RISK_CRITICAL


def test_risk_level_negative_is_critical():
    assert risk_level(-1.0) == RISK_CRITICAL


def test_risk_level_infinite_and_huge_are_low():
    assert risk_level(math.inf) == RISK_LOW
    assert risk_level(1e12) == RISK_LOW


def test_risk_level_refuses_nan():
    with pytest.raises(ValueError):
        risk_level(math.nan)


def test_risk_level_is_pure():
    """Same input, same answer, no state between calls."""
    assert [risk_level(r) for r in (2.0, 0.5, 2.0, 0.5)] == [RISK_LOW, RISK_CRITICAL, RISK_LOW, RISK_CRITICAL]


def test_ratio_and_level_together_on_the_brief_example():
    """Remaining 4h, available 2h -> 0.5 -> CRITICAL; available 6h -> 1.5 -> MODERATE."""
    physics = task("Physics", MONDAY, 6)
    assert risk_level(deadline_risk_ratio(physics, scheduled(physics, 2), week(monday=2), MONDAY)) == RISK_CRITICAL
    physics = task("Physics", WEDNESDAY, 6)
    slots = week(monday=2, tuesday=2, wednesday=2)
    assert risk_level(deadline_risk_ratio(physics, scheduled(physics, 2), slots, MONDAY)) == RISK_MODERATE


def test_nothing_remaining_classifies_as_low_without_a_special_case():
    done = task("Done", TUESDAY, 2)
    assert risk_level(deadline_risk_ratio(done, scheduled(done, 2), week(monday=2), MONDAY)) == RISK_LOW
