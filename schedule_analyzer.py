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
from datetime import date
from typing import Iterable, List, Optional

from models import Assignment, TimeSlot
from schedule_builder import BREAK_LABEL, ScheduleResult

_WIDTH = 32
_RULE = "-" * _WIDTH
_BANNER = "=" * _WIDTH

# Assignment-level status. Plain strings rather than emoji so the CLI
# report prints the same on every console.
STATUS_COMPLETE = "COMPLETE"        # every required hour is on the schedule
STATUS_PARTIAL = "PARTIAL"          # some hours are on the schedule, not all
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
            return STATUS_PARTIAL
        return STATUS_UNSCHEDULED


def scheduled_hours_for_assignment(result: ScheduleResult, assignment: Assignment) -> float:
    """
    Find every scheduled block belonging to this assignment and add
    their durations together, in hours.

        Monday     Physics  1.5h
        Tuesday    Physics  2.0h
        Wednesday  Math     1.0h

        scheduled_hours_for_assignment(result, physics) -> 3.5

    Breaks are never counted, even for an assignment that happens to
    be called "Break", and blocks belonging to other assignments are
    never counted. A block belongs to an assignment when its label is
    the assignment's name.
    """
    minutes = sum(
        block.end_minute - block.start_minute
        for blocks in result.by_date.values()
        for block in blocks
        if block.label == assignment.name and block.label != BREAK_LABEL
    )
    return minutes / 60


def analyze_assignments(
    result: ScheduleResult, assignments: Iterable[Assignment]
) -> List[AssignmentAnalysis]:
    """
    One AssignmentAnalysis per active assignment, in the order given.
    Completed assignments are skipped: the scheduler never places
    them, so there is nothing to report.
    """
    return [analyze_assignment(result, a) for a in assignments if not a.completed]


def analyze_assignment(result: ScheduleResult, assignment: Assignment) -> AssignmentAnalysis:
    """
    The chain for one assignment:

        required hours -> scheduled hours -> remaining hours -> status

    A completed assignment requires no study time, so it reports zero
    required hours and comes out COMPLETE whatever the schedule holds.
    A negative estimate counts as zero, as everywhere else.
    """
    required = 0.0 if assignment.completed else max(assignment.estimated_hours, 0.0)
    return AssignmentAnalysis(
        assignment=assignment,
        required_hours=required,
        scheduled_hours=scheduled_hours_for_assignment(result, assignment),
    )


def assignment_status(result: ScheduleResult, assignment: Assignment) -> str:
    """
    COMPLETE when every required hour is on the schedule, PARTIAL when
    some are, UNSCHEDULED when none are.

        Physics  required 4h, scheduled 4h    -> COMPLETE
        Math     required 4h, scheduled 2.5h  -> PARTIAL
        CS       required 3h, scheduled 0h    -> UNSCHEDULED

    A zero-hour assignment requires no study time, so it is COMPLETE;
    so is one already marked completed.
    """
    return analyze_assignment(result, assignment).status


def at_risk_assignments(
    result: ScheduleResult, assignments: Iterable[Assignment]
) -> List[Assignment]:
    """
    The assignments that need attention: not completed, and not fully
    scheduled. Returned in the order given.

        Completed assignment              not at risk
        100% scheduled                    not at risk
        Partially scheduled               AT RISK
        0% scheduled                      AT RISK
        Zero-hour assignment              not at risk (nothing to do)
        Fully scheduled but due today     not at risk (the work is placed)

    An overdue assignment that is not fully scheduled is at risk too:
    the deadline being behind it makes the missing hours more urgent,
    not less. This is the simple first rule; a later version can
    weigh how close the deadline is against how much is missing.
    """
    return [
        a for a in assignments
        if not a.completed and assignment_status(result, a) != STATUS_COMPLETE
    ]


def format_analysis(
    result: ScheduleResult,
    assignments: Iterable[Assignment],
    time_slots: Optional[Iterable[TimeSlot]] = None,
    today: Optional[date] = None,
) -> str:
    """
    Return a readable analysis of the generated study plan: the four
    totals, then one entry per active assignment with its status,
    scheduled hours, and, when work remains, the remaining hours and
    the deadline risk.

    Every number comes from the functions above; nothing is
    recalculated here. The Risk line needs the study slots and today
    (to know how much time exists before the deadline), so it is
    printed only when `time_slots` is given.
    """
    # The optimizer builds on this module, so import it here rather
    # than at the top to avoid a circular import.
    from schedule_optimizer import deadline_risk_ratio, risk_level

    assignments = list(assignments)
    lines: List[str] = [
        _BANNER,
        "STUDYFLOW ANALYSIS".center(_WIDTH).rstrip(),
        _BANNER,
        "",
        f"Required work:   {total_required_hours(assignments):6.1f}h",
        f"Scheduled work:  {total_scheduled_hours(result):6.1f}h",
        f"Unscheduled work:{total_unscheduled_hours(result):6.1f}h",
        f"Completion:      {completion_percentage(result, assignments):6.1f}%",
        "",
        _RULE,
        "ASSIGNMENTS",
        _RULE,
    ]

    rows = analyze_assignments(result, assignments)
    if not rows:
        lines += ["", "No active assignments to analyse."]
        return "\n".join(lines)

    for row in rows:
        lines += ["", row.assignment.name,
                  f"  Status: {row.status}",
                  f"  Scheduled: {row.scheduled_hours:.1f}h"]
        if row.remaining_hours > 0:
            lines.append(f"  Remaining: {row.remaining_hours:.1f}h")
            if time_slots is not None:
                ratio = deadline_risk_ratio(row.assignment, result, time_slots, today or date.today())
                lines.append(f"  Risk: {risk_level(ratio)}")
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
