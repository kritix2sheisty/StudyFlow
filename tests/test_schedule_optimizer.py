"""
tests/test_schedule_optimizer.py
Pytest suite for schedule_optimizer.

Phase 4 starts with available_hours_before_deadline(): how much study
time exists between today and an assignment's due date. The first
four tests are the ones from the brief; the rest pin the edges.
"""

from datetime import date, timedelta

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_optimizer import available_hours_before_deadline

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
