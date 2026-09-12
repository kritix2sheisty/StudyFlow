"""
StudyFlow/plan_view.py
Turns a StudyPlan (the engine's result) into the plain values the
Reflex pages render. Nothing here decides anything about the plan;
every number comes from study_plan.py, schedule_analyzer.py and
schedule_optimizer.py.

Why a separate step: Reflex state holds strings, numbers, lists and
dicts, not ScheduleResult or Assignment objects. This module is the
one place where the engine's dataclasses become page data, and it is
unit-tested against the engine with a controlled example.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List

from models import Assignment, TimeSlot
from schedule_builder import BREAK_LABEL
from schedule_optimizer import deadline_risk_ratio, risk_level
from study_plan import StudyPlan


@dataclass
class Block:
    """One entry on a day: a study period or a break."""
    time: str       # "4 PM–5:30 PM", from ScheduledBlock.format_time_range()
    label: str      # the assignment name, or "Break"
    is_break: str   # "yes" / "no"; a string so every field renders the same way


@dataclass
class Day:
    """One day of the plan and its blocks in time order."""
    label: str      # "Monday 14 Sep"
    iso: str        # "2026-09-14"
    blocks: List[Block]


def blocks_for(plan: StudyPlan, day: date) -> List[Block]:
    return [
        Block(time=b.format_time_range(), label=b.label, is_break="yes" if b.label == BREAK_LABEL else "no")
        for b in plan.schedule.by_date.get(day, [])
    ]


def days_of(plan: StudyPlan) -> List[Day]:
    """Every day that has at least one block, earliest first."""
    return [
        Day(label=day.strftime("%A %d %b"), iso=day.isoformat(), blocks=blocks_for(plan, day))
        for day in sorted(plan.schedule.by_date)
    ]


def today_blocks(plan: StudyPlan, today: date) -> List[Dict[str, str]]:
    """Today's blocks as dicts, the shape the dashboard's plan rows already use."""
    return [{"time": b.time, "label": b.label, "is_break": b.is_break} for b in blocks_for(plan, today)]


def totals(plan: StudyPlan) -> Dict[str, str]:
    return {
        "required": f"{plan.required_hours:.1f}",
        "scheduled": f"{plan.scheduled_hours:.1f}",
        "unscheduled": f"{plan.unscheduled_hours:.1f}",
        "completion": f"{plan.completion:.0f}",
    }


@dataclass
class StatusRow:
    """How one assignment fared in the plan, ready for the page."""
    id: str
    name: str
    subject: str
    status: str         # COMPLETE / PARTIAL / UNSCHEDULED, from the analyzer
    scheduled: str      # hours, one decimal
    required: str
    remaining: str
    percent: int        # of this assignment's required hours that are scheduled
    risk: str           # CRITICAL / HIGH / MODERATE / LOW, from the optimizer
    due: str            # ISO date


def status_rows(plan: StudyPlan, time_slots: Iterable[TimeSlot], today: date) -> List[StatusRow]:
    """
    One row per active assignment: status and percent from the
    analyzer, risk from the optimizer. Nothing remaining gives an
    infinite ratio, which risk_level() reports as LOW.
    """
    slots = list(time_slots)
    rows = []
    for row in plan.analyses:
        ratio = deadline_risk_ratio(row.assignment, plan.schedule, slots, today)
        rows.append(StatusRow(
            id=str(row.assignment.id) if row.assignment.id is not None else "",
            name=row.assignment.name,
            subject=row.assignment.subject,
            status=row.status,
            scheduled=f"{row.scheduled_hours:.1f}",
            required=f"{row.required_hours:.1f}",
            remaining=f"{row.remaining_hours:.1f}",
            percent=round(row.percent_scheduled),
            risk=risk_level(ratio),
            due=row.assignment.due_date.isoformat(),
        ))
    return rows


def risk_by_name(rows: Iterable[StatusRow]) -> Dict[str, str]:
    """Assignment name -> risk word, for stamping onto the assignment cards."""
    return {r.name: r.risk for r in rows}


def has_unscheduled(plan: StudyPlan) -> bool:
    return bool(plan.schedule.unscheduled)


def guard_message(assignments: List[Assignment], time_slots: List[TimeSlot]) -> str:
    """Why a plan cannot be generated yet, or an empty string if it can."""
    if not assignments:
        return "Add some assignments before generating your study plan."
    if not time_slots:
        return "Add your available study times before generating a study plan."
    return ""


# ---------------------------------------------------------------------
# Plan freshness
# ---------------------------------------------------------------------

def plan_input_fingerprint(assignments: Iterable[Assignment], time_slots: Iterable[TimeSlot]) -> str:
    """
    A SHA-256 hex digest of every stored value that can change a plan:
    each assignment's id, name, subject, due date, hours, priority and
    completed flag, and each slot's id, weekday and hours. The entries
    are sorted before hashing, so database order does not matter.

    It answers one question only: "is this the same input data that
    produced the plan?" Compare the value saved when a plan was
    generated with the value for the database now; if they differ the
    plan describes data the student no longer has. It knows nothing
    about how the plan is built.
    """
    payload = {
        "assignments": sorted(
            ([a.id, a.name, a.subject, a.due_date.isoformat(), float(a.estimated_hours),
              int(a.priority), bool(a.completed)] for a in assignments),
            key=repr,
        ),
        "slots": sorted(
            ([t.id, int(t.weekday), t.start_hour, t.end_hour] for t in time_slots),
            key=repr,
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
