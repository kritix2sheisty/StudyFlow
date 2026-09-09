"""
schedule_builder.py
Phase 3 — turns a prioritized assignment list + a set of recurring
weekly time slots into an actual day-by-day, time-blocked schedule.

=====================================================================
The algorithm
=====================================================================

StudyFlow uses a GREEDY, DEADLINE-AWARE scheduler. Greedy means it
never backtracks: each decision is made once, from what looks best at
that moment, and is never revisited. That makes it simple to explain,
fast to run, and predictable. It also means the result is not
guaranteed to be the best possible schedule (see "Limitations").

  1. Drop completed assignments and rank the rest with the Phase 2
     scorer (scheduler.prioritize_assignments).
  2. Expand the student's recurring weekly TimeSlots into concrete,
     dated blocks for the next `days_ahead` days, in time order.
  3. Re-order the ranked list by due date, earliest first, with the
     Phase 2 rank breaking ties. This is earliest-deadline-first (EDF).
  4. For each assignment in that order, walk the blocks in time order
     and pour work into every block dated on or before its due date,
     splitting across blocks as needed, until the assignment is fully
     placed or no eligible time is left. Work already overdue has no
     date limit: its deadline is gone, so it simply goes as early as
     possible.
  5. Between two chunks of work in the same block, insert a break of
     `break_minutes`. A break is never shortened; if a full break plus
     any work would not fit, the leftover minutes stay free.
  6. Whatever could not be placed is reported as unscheduled, with the
     hours left over, rather than shrinking estimates or refusing to
     build a partial schedule.

Why re-order by deadline when Phase 2 already ranked everything?
Phase 2 answers "what should I work on next?", and for that a blend
of urgency, importance and size is right. Phase 3 answers "which hour
goes where?", and there a classical result applies: on a single
resource where work can be split, placing tasks earliest-deadline-
first meets every deadline whenever any order can. Filling in Phase 2
order does not have that property. A 10-hour HIGH exam prep due
Friday outranks a 1-hour LOW worksheet due Thursday (that is the
prioritizer's promise 6), and if it is placed first it swallows
Monday to Friday and the worksheet never gets its hour, even though
one was trivially available. Phase 2 still decides the order among
assignments that share a due date, and so which of them is cut when
there is not enough time.

Rules settled in the Phase 3 review:
  - Work is never placed after its due date. A slot on the due date
    itself is fine: due dates are whole days, not times.
  - An assignment that needs more time than exists before its due
    date gets whatever does exist and the rest is flagged.
  - Overdue work is placed as early as possible with no date limit.
  - A bigger-than-any-slot assignment is split across blocks and days.
  - Breaks go only between two chunks of work in the same block, are
    never shortened, and are never left dangling at the end of a day.

Limitations (deliberate, for a first version):
  - Greedy fills the earliest eligible block completely before moving
    on, so work is front-loaded rather than spread evenly over the
    days before a deadline. Three hours due Tuesday become two hours
    Monday and one Tuesday, not ninety minutes each day.
  - The EDF guarantee ignores breaks, so a set of assignments that
    fits exactly can still lose a few minutes to a break and end up
    with a small remainder flagged.
  - There is no cap on hours per day and no preference for variety,
    so a long block can be one subject end to end.
  - "Optimal" is not defined yet. Once StudyFlow decides what a
    better schedule means (fewer late hours? more even days? fewer
    context switches?), a search or optimisation pass can replace the
    greedy fill. Until then, greedy is the honest choice.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from models import Assignment, TimeSlot, Weekday
from scheduler import prioritize_assignments

DEFAULT_BREAK_MINUTES = 15
DEFAULT_DAYS_AHEAD = 7
BREAK_LABEL = "Break"


@dataclass
class ScheduledBlock:
    """One entry on the final schedule: a chunk of time with a label."""
    start_minute: int   # minutes since midnight
    end_minute: int
    label: str           # assignment name, or BREAK_LABEL

    def format_time_range(self) -> str:
        return f"{_format_minutes(self.start_minute)}–{_format_minutes(self.end_minute)}"


@dataclass
class ScheduleResult:
    """Everything build_schedule() produces."""
    by_date: Dict[date, List[ScheduledBlock]] = field(default_factory=dict)
    unscheduled: List[Tuple[Assignment, float]] = field(default_factory=list)
    # unscheduled: (assignment, remaining_hours_that_didn't_fit)


class _WorkBlock:
    """
    Internal mutable tracker for one concrete occurrence of a TimeSlot
    on one specific date — how much of it is left to fill.
    """
    def __init__(self, block_date: date, start_hour: int, end_hour: int):
        self.date = block_date
        self.start = start_hour * 60   # minutes since midnight
        self.end = end_hour * 60
        self.cursor = self.start       # moves forward as the block fills

    @property
    def remaining(self) -> int:
        return self.end - self.cursor

    @property
    def has_work(self) -> bool:
        return self.cursor > self.start


def _format_minutes(total_minutes: int) -> str:
    """730 -> '12:10 PM' style formatting."""
    hour24, minute = divmod(total_minutes, 60)
    suffix = "AM" if hour24 < 12 else "PM"
    hour12 = hour24 % 12 or 12
    return f"{hour12}:{minute:02d} {suffix}" if minute else f"{hour12} {suffix}"


def _generate_week_blocks(
    time_slots: List[TimeSlot], start_date: date, days_ahead: int
) -> List[_WorkBlock]:
    """
    Expand recurring weekly TimeSlots into concrete dated blocks over
    the next `days_ahead` days (including today), in chronological order.
    """
    blocks: List[_WorkBlock] = []
    for offset in range(days_ahead):
        current_date = start_date + timedelta(days=offset)
        current_weekday = Weekday(current_date.weekday())
        for slot in time_slots:
            if slot.weekday == current_weekday:
                blocks.append(_WorkBlock(current_date, slot.start_hour, slot.end_hour))
    blocks.sort(key=lambda b: (b.date, b.start))
    return blocks


def _placement_order(assignments: List[Assignment], today: date) -> List[Assignment]:
    """
    Earliest due date first; the Phase 2 rank breaks ties. Overdue work
    sorts with work due today, since its deadline is already here.
    Python's sort is stable, so the Phase 2 order survives within a
    due date.
    """
    ranked = prioritize_assignments(assignments, today=today)
    return sorted(ranked, key=lambda a: max(a.due_date, today))


def _last_eligible_date(assignment: Assignment, today: date) -> Optional[date]:
    """The latest date work may be placed on, or None for no limit."""
    if assignment.due_date < today:
        return None   # already overdue: as soon as possible, wherever that is
    return assignment.due_date


def _place(
    assignment: Assignment,
    blocks: List[_WorkBlock],
    today: date,
    break_minutes: int,
    result: ScheduleResult,
) -> None:
    """Pour one assignment into the eligible blocks, earliest first."""
    remaining = round(assignment.estimated_hours * 60)
    if remaining <= 0:
        return
    last_date = _last_eligible_date(assignment, today)

    for block in blocks:
        if remaining <= 0:
            break
        if last_date is not None and block.date > last_date:
            break   # blocks are in date order; nothing later is eligible
        free = block.remaining
        if free <= 0:
            continue

        if block.has_work:
            # A break separates this chunk from the previous one. If the
            # full break would leave no room for work, skip the block.
            if free <= break_minutes:
                continue
            _append(result, block, break_minutes, BREAK_LABEL)
            free -= break_minutes

        chunk = min(remaining, free)
        _append(result, block, chunk, assignment.name)
        remaining -= chunk

    if remaining > 0:
        result.unscheduled.append((assignment, remaining / 60))


def _append(result: ScheduleResult, block: _WorkBlock, minutes: int, label: str) -> None:
    start = block.cursor
    end = start + minutes
    result.by_date.setdefault(block.date, []).append(ScheduledBlock(start, end, label))
    block.cursor = end


def build_schedule(
    assignments: List[Assignment],
    time_slots: List[TimeSlot],
    today: Optional[date] = None,
    break_minutes: int = DEFAULT_BREAK_MINUTES,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
) -> ScheduleResult:
    """
    Build a deadline-aware schedule for the next `days_ahead` days.

    See the module docstring for the algorithm. Assignments that do
    not fit on or before their due date end up in result.unscheduled,
    along with how many hours were left over.
    """
    today = today or date.today()
    blocks = _generate_week_blocks(time_slots, today, days_ahead)
    result = ScheduleResult()

    for assignment in _placement_order(assignments, today):
        _place(assignment, blocks, today, break_minutes, result)

    _sort_days(result)
    return result


def _sort_days(result: ScheduleResult) -> None:
    """
    Later assignments can fill leftover room in earlier blocks, so a
    day's entries are not necessarily appended in time order when the
    day has more than one slot. Sort each day by start time.
    """
    for blocks in result.by_date.values():
        blocks.sort(key=lambda b: b.start_minute)


def format_schedule(result: ScheduleResult) -> str:
    """Render a ScheduleResult as readable text, grouped by day."""
    lines: List[str] = []
    for day in sorted(result.by_date):
        lines.append(day.strftime("%A %Y-%m-%d"))
        for b in result.by_date[day]:
            lines.append(f"  {b.format_time_range()}  {b.label}")
        lines.append("")

    if result.unscheduled:
        lines.append("Could not fit on or before the due date:")
        for assignment, hours_left in result.unscheduled:
            lines.append(
                f"  - {assignment.name}: {hours_left:.2f}h unscheduled "
                f"(due {assignment.due_date.isoformat()})"
            )

    return "\n".join(lines).rstrip()
