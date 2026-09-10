"""
schedule_analyzer.py
Phase 3.3 — schedule quality.

The builder answers "can I fit these assignments into the available
study periods?". This module answers "how well did I schedule them?"
by reading a finished ScheduleResult. It never changes the schedule;
it only measures it. Later, these measurements are what will let
StudyFlow compare two candidate schedules and pick the better one.

Hours everywhere are floats: 90 minutes is 1.5.
"""

from typing import Iterable

from models import Assignment
from schedule_builder import BREAK_LABEL, ScheduleResult


def total_scheduled_hours(result: ScheduleResult) -> float:
    """
    Hours of actual work on the schedule, across every day. Breaks are
    time on the timetable but not work, so they are not counted.
    """
    minutes = sum(
        block.end_minute - block.start_minute
        for blocks in result.by_date.values()
        for block in blocks
        if block.label != BREAK_LABEL
    )
    return minutes / 60


def total_unscheduled_hours(result: ScheduleResult) -> float:
    """Hours of work that could not be placed before their due dates."""
    return sum(hours_left for _, hours_left in result.unscheduled)


def total_required_hours(assignments: Iterable[Assignment]) -> float:
    """
    Hours the assignments call for in total. Completed assignments are
    not required work, and a negative estimate counts as zero, the
    same way the scheduler treats it.
    """
    return sum(
        max(a.estimated_hours, 0.0)
        for a in assignments
        if not a.completed
    )


def completion_percentage(result: ScheduleResult, assignments: Iterable[Assignment]) -> float:
    """
    How much of the required work the schedule covers:

        scheduled hours / total required hours * 100

    `assignments` must be the same list that was given to
    build_schedule(), so that required and scheduled describe the same
    work. With nothing required (no assignments, or only completed or
    zero-hour ones) there is no unfinished work, so the answer is 100.
    """
    required = total_required_hours(assignments)
    if required == 0:
        return 100.0
    return total_scheduled_hours(result) / required * 100
