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

from dataclasses import dataclass
from typing import Dict, Iterable, List

from models import Assignment
from schedule_builder import BREAK_LABEL, ScheduleResult

# Assignment-level status. Plain strings rather than emoji so the CLI
# report prints the same on every console.
STATUS_COMPLETE = "OK"            # every required hour is on the schedule
STATUS_AT_RISK = "AT RISK"        # some hours are on the schedule, not all
STATUS_UNSCHEDULED = "UNSCHEDULED"  # none of it is


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


# ---------------------------------------------------------------------
# Assignment-level analysis (Phase 3.4)
# ---------------------------------------------------------------------
#
#   Assignment -> ScheduledBlocks -> hours scheduled -> hours remaining -> status
#
# Blocks carry the assignment's name as their label, so an assignment's
# scheduled hours are the sum of the blocks labelled with its name.
# Two assignments that share a name would be merged; the CLI stores
# names as typed, so keep them distinct.


@dataclass
class AssignmentAnalysis:
    """How one assignment fared on the schedule."""
    assignment: Assignment
    required_hours: float
    scheduled_hours: float

    @property
    def remaining_hours(self) -> float:
        return max(self.required_hours - self.scheduled_hours, 0.0)

    @property
    def percent_scheduled(self) -> float:
        if self.required_hours == 0:
            return 100.0   # nothing to do counts as done
        return min(self.scheduled_hours / self.required_hours, 1.0) * 100

    @property
    def status(self) -> str:
        if self.remaining_hours == 0:
            return STATUS_COMPLETE
        if self.scheduled_hours > 0:
            return STATUS_AT_RISK
        return STATUS_UNSCHEDULED


def scheduled_hours_by_name(result: ScheduleResult) -> Dict[str, float]:
    """Hours of work per label on the schedule, breaks excluded."""
    minutes: Dict[str, int] = {}
    for blocks in result.by_date.values():
        for block in blocks:
            if block.label != BREAK_LABEL:
                minutes[block.label] = minutes.get(block.label, 0) + (block.end_minute - block.start_minute)
    return {name: m / 60 for name, m in minutes.items()}


def analyze_assignments(
    result: ScheduleResult, assignments: Iterable[Assignment]
) -> List[AssignmentAnalysis]:
    """
    One AssignmentAnalysis per active assignment, in the order given.
    Completed assignments are skipped: the scheduler never places
    them, so there is nothing to report.
    """
    scheduled = scheduled_hours_by_name(result)
    return [
        AssignmentAnalysis(
            assignment=a,
            required_hours=max(a.estimated_hours, 0.0),
            scheduled_hours=scheduled.get(a.name, 0.0),
        )
        for a in assignments
        if not a.completed
    ]


def at_risk(analyses: Iterable[AssignmentAnalysis]) -> List[AssignmentAnalysis]:
    """Every assignment that is not fully scheduled, at risk or worse."""
    return [x for x in analyses if x.status != STATUS_COMPLETE]


def format_analysis(analyses: List[AssignmentAnalysis]) -> str:
    """
    The per-assignment table:

        Physics Lab        100% scheduled   OK
        Math Homework       50% scheduled   AT RISK
        Computer Science     0% scheduled   UNSCHEDULED
    """
    if not analyses:
        return "No active assignments to analyse."
    width = max(len(x.assignment.name) for x in analyses)
    lines = ["StudyFlow Schedule Analysis", ""]
    for x in analyses:
        lines.append(
            f"{x.assignment.name:<{width}}  {x.percent_scheduled:3.0f}% scheduled   {x.status}"
        )
    return "\n".join(lines)


def format_summary(result: ScheduleResult, assignments: Iterable[Assignment]) -> str:
    """
    The totals block:

        Schedule Summary
        Required:       8.0h
        Scheduled:      6.0h
        Unscheduled:    2.0h
        Completion:    75.0%
    """
    assignments = list(assignments)
    return "\n".join([
        "Schedule Summary",
        f"Required:    {total_required_hours(assignments):6.1f}h",
        f"Scheduled:   {total_scheduled_hours(result):6.1f}h",
        f"Unscheduled: {total_unscheduled_hours(result):6.1f}h",
        f"Completion:  {completion_percentage(result, assignments):6.1f}%",
    ])
