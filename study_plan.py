"""
study_plan.py
The StudyFlow weekly workflow: one call that turns a student's
assignments and study availability into a schedule and an
explanation of it.

    generate_study_plan()
           |
           +-- prioritize_assignments()   what to work on next
           +-- build_schedule()           where each hour goes
           +-- total_*_hours(),
           |   completion_percentage()    how much of the work fits
           +-- analyze_assignments()      how each assignment fared
           +-- at_risk_assignments()      what needs attention

This module is an orchestrator. It holds no scheduling or analysis
logic of its own; every number in a StudyPlan comes from the module
responsible for it, so each of those keeps a single job.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from models import Assignment, TimeSlot
from schedule_analyzer import (
    AssignmentAnalysis,
    analyze_assignments,
    at_risk_assignments,
    completion_percentage,
    total_required_hours,
    total_scheduled_hours,
    total_unscheduled_hours,
)
from schedule_builder import (
    DEFAULT_BREAK_MINUTES,
    DEFAULT_DAYS_AHEAD,
    ScheduleResult,
    build_schedule,
    format_timetable,
)
from scheduler import prioritize_assignments


@dataclass
class StudyPlan:
    """Everything generate_study_plan() produces, in one place."""
    today: date
    assignments: List[Assignment]              # exactly what was given
    prioritized: List[Assignment]              # active ones, most urgent first
    schedule: ScheduleResult
    analyses: List[AssignmentAnalysis] = field(default_factory=list)
    at_risk: List[Assignment] = field(default_factory=list)
    required_hours: float = 0.0
    scheduled_hours: float = 0.0
    unscheduled_hours: float = 0.0
    completion: float = 100.0                  # percent


def generate_study_plan(
    assignments: List[Assignment],
    time_slots: List[TimeSlot],
    today: Optional[date] = None,
    break_minutes: int = DEFAULT_BREAK_MINUTES,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
) -> StudyPlan:
    """
    Prioritize, schedule, analyze, flag. Returns a StudyPlan holding
    the results of each step together.

    `today` defaults to the real date, as it does for the scheduler;
    pass it explicitly in tests.
    """
    today = today or date.today()
    assignments = list(assignments)

    prioritized = prioritize_assignments(assignments, today=today)
    schedule = build_schedule(
        assignments, time_slots, today=today,
        break_minutes=break_minutes, days_ahead=days_ahead,
    )

    return StudyPlan(
        today=today,
        assignments=assignments,
        prioritized=prioritized,
        schedule=schedule,
        analyses=analyze_assignments(schedule, assignments),
        at_risk=at_risk_assignments(schedule, assignments),
        required_hours=total_required_hours(assignments),
        scheduled_hours=total_scheduled_hours(schedule),
        unscheduled_hours=total_unscheduled_hours(schedule),
        completion=completion_percentage(schedule, assignments),
    )


# ---------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------

_WIDTH = 32
_RULE = "-" * _WIDTH
_BANNER = "=" * _WIDTH


def _section(title: str) -> List[str]:
    return ["", _RULE, title, _RULE]


def format_study_plan(plan: StudyPlan) -> str:
    """
    The weekly report: the timetable, the progress numbers, and the
    assignments that need attention. Plain text only, so it prints
    the same on every console.
    """
    lines: List[str] = [
        _BANNER,
        "STUDYFLOW".center(_WIDTH).rstrip(),
        "WEEKLY STUDY PLAN".center(_WIDTH).rstrip(),
        _BANNER,
        f"Week of {plan.today.strftime('%A %Y-%m-%d')}",
    ]

    lines += _section("THIS WEEK")
    timetable = format_timetable(plan.schedule)
    lines.append(_uppercase_day_headings(timetable) if timetable else "Nothing scheduled.")

    lines += _section("PROGRESS")
    lines += [
        f"Required work:   {plan.required_hours:6.1f}h",
        f"Scheduled work:  {plan.scheduled_hours:6.1f}h",
        f"Unscheduled work:{plan.unscheduled_hours:6.1f}h",
        f"Completion:      {plan.completion:6.1f}%",
    ]

    lines += _section("AT-RISK ASSIGNMENTS")
    if not plan.at_risk:
        lines.append("None. Every assignment is fully scheduled.")
    else:
        remaining = {row.assignment.name: row.remaining_hours for row in plan.analyses}
        for a in plan.at_risk:
            lines += [a.name, f"{remaining[a.name]:.1f}h remaining (due {a.due_date.isoformat()})", ""]
        lines.pop()   # no blank line after the last entry

    return "\n".join(lines)


def _uppercase_day_headings(timetable: str) -> str:
    """'Monday 2026-08-17' headings become 'MONDAY 2026-08-17'; block lines are left alone."""
    return "\n".join(
        line if line.startswith("  ") else line.upper()
        for line in timetable.splitlines()
    )
