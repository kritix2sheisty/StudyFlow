"""
schedule_optimizer.py
Phase 4 — intelligent scheduling.

This module will grow into the part of StudyFlow that makes the
schedule smarter. It starts with one piece of information the rest
of the system does not have yet: how much study time actually exists
between today and an assignment's deadline.

    available_hours_before_deadline()
            |
            v
      risk calculation        (next)
            |
            v
        optimizer             (later)
            |
            v
        schedule

Everything here is analysis and calculation. Nothing in this module
decides the final schedule; that stays in schedule_builder.py, so
each layer can be tested and improved on its own.
"""

from datetime import date, timedelta
from typing import Iterable

from models import Assignment, TimeSlot, Weekday


def available_hours_before_deadline(
    assignment: Assignment,
    time_slots: Iterable[TimeSlot],
    today: date,
) -> float:
    """
    Hours of study time on the calendar from today up to and including
    the assignment's due date.

        Today: Monday. Due Thursday.
        Monday 2h, Tuesday 3h, Wednesday 1h, Thursday 2h, Friday 3h
        -> 8.0  (Monday to Thursday; Friday is after the deadline)

    Same rule as the scheduler's _can_schedule_on(): a study period
    on the due date itself counts, because due dates are whole days.
    Today's slots count in full; StudyFlow works in dates, not times
    of day. An assignment that is already overdue has no time left
    before its deadline, so the answer is 0.

    This is the raw capacity, not what is free: other assignments may
    already be using some of it. Comparing it with the hours an
    assignment still needs is the next step, the risk calculation.
    """
    slots = list(time_slots)
    if assignment.due_date < today or not slots:
        return 0.0

    hours = 0.0
    day = today
    while day <= assignment.due_date:
        weekday = Weekday(day.weekday())
        hours += sum(slot.duration_hours for slot in slots if slot.weekday == weekday)
        day += timedelta(days=1)
    return hours
