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

import math
from datetime import date, timedelta
from typing import Iterable

from models import Assignment, TimeSlot, Weekday
from schedule_analyzer import analyze_assignment
from schedule_builder import ScheduleResult


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


def free_hours_before_deadline(
    assignment: Assignment,
    result: ScheduleResult,
    time_slots: Iterable[TimeSlot],
    today: date,
) -> float:
    """
    Study time before the deadline that nothing is using yet:

        raw capacity before the deadline (available_hours_before_deadline)
        minus every block already on the schedule on those days

    Every block counts as occupied, whoever it belongs to and whether
    it is work or a break: a 15-minute break is 15 minutes the student
    cannot study in. The assignment's own placed hours are occupied
    too; they are not free to absorb what remains. Blocks after the
    due date are ignored, since they cannot help before it. Never
    negative: if the schedule holds more than the slots do (slots
    edited after planning), the answer is 0.
    """
    raw = available_hours_before_deadline(assignment, time_slots, today)
    occupied_minutes = sum(
        block.end_minute - block.start_minute
        for day, blocks in result.by_date.items()
        if day <= assignment.due_date
        for block in blocks
    )
    return max(raw - occupied_minutes / 60, 0.0)


def deadline_risk_ratio(
    assignment: Assignment,
    result: ScheduleResult,
    time_slots: Iterable[TimeSlot],
    today: date,
) -> float:
    """
    How the time still free before the deadline compares with the work
    still to do:

        free hours before deadline / remaining hours

        remaining 4h, 2h free  -> 0.5   (not enough time)
        remaining 4h, 6h free  -> 1.5   (some room to spare)
        remaining 1h, 0h free  -> 0.0   (every hour before the deadline
                                         is already taken)

    Remaining hours come from the analyzer: required minus what is
    already on the schedule, with completed assignments and negative
    estimates counting as nothing required. Free hours come from
    free_hours_before_deadline(), so time other assignments have
    consumed, and this assignment's own placed hours, no longer count
    as available.

    When nothing remains (completed, zero-hour, or fully scheduled)
    the ratio has no meaning as a fraction, so it is reported as
    infinity: there is unlimited time for no work. That keeps the
    value comparable, and any threshold on it lands on the safe side.

    An overdue assignment with work left has no time before its
    deadline, so the ratio is 0.
    """
    remaining = analyze_assignment(result, assignment).remaining_hours
    if remaining == 0:
        return math.inf
    return free_hours_before_deadline(assignment, result, time_slots, today) / remaining


# Risk levels, from a ratio of available time to remaining work.
RISK_CRITICAL = "CRITICAL"   # less time than work:            ratio < 1.0
RISK_HIGH = "HIGH"           # enough, with little to spare:   1.0 <= ratio < 1.5
RISK_MODERATE = "MODERATE"   # some room:                      1.5 <= ratio < 2.0
RISK_LOW = "LOW"             # at least twice the time needed: ratio >= 2.0

HIGH_THRESHOLD = 1.0
MODERATE_THRESHOLD = 1.5
LOW_THRESHOLD = 2.0


def risk_level(ratio: float) -> str:
    """
    Turn a deadline risk ratio into a word a student can act on.

        0.5 -> CRITICAL     1.0 -> HIGH     1.5 -> MODERATE     2.0 -> LOW

    Each boundary belongs to the safer side: exactly 1.0 is HIGH, not
    CRITICAL, because the time does cover the work; exactly 2.0 is
    LOW.

    Unusual values:
      - 0 is CRITICAL: no time at all before the deadline.
      - A negative ratio cannot come from deadline_risk_ratio(), but
        less than no time is still no time, so it is CRITICAL.
      - Infinity (nothing remaining) and any very large ratio are LOW.
      - NaN is refused with a ValueError. Every comparison with NaN is
        false, so it would otherwise fall through to LOW and hide a
        bug upstream.
    """
    if math.isnan(ratio):
        raise ValueError("risk ratio is NaN; the ratio calculation upstream went wrong")
    if ratio < HIGH_THRESHOLD:
        return RISK_CRITICAL
    if ratio < MODERATE_THRESHOLD:
        return RISK_HIGH
    if ratio < LOW_THRESHOLD:
        return RISK_MODERATE
    return RISK_LOW
