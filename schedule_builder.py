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
  3b. Within one due date, place the assignments that can still be
     finished before the others. "Can be finished" is judged when the
     group's turn comes, against the minutes actually still free in
     the blocks that assignment may use (v1.1, "achievable first";
     see below). The Phase 2 rank still orders each half.
  4. For each assignment in that order, walk the blocks in time order
     and pour work into every block dated on or before its due date,
     splitting across blocks as needed, until the assignment is fully
     placed or no eligible time is left. Work already overdue has no
     date limit: its deadline is gone, so it simply goes as early as
     possible.
  5. Between two chunks of work in the same block, insert a break of
     `break_minutes`. A break is never shortened, and the chunk after
     it is at least as long as the break; if both would not fit, the
     leftover minutes stay free.
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
there is not enough time, with one exception.

Achievable first (v1.1). Two assignments due the same day compete
for the same hours, and Phase 2 puts the bigger one first because it
needs starting sooner. When the bigger one cannot be finished in the
time that exists anyway, that order lets it swallow every hour and
leave the smaller one, which could have been finished, with nothing:
a 20-hour project and a 2-hour exercise due the same day, six hours
free, gave the project all six and the exercise none. So within a
due date, assignments whose whole estimate fits in the minutes still
free at that point are placed first, then the ones that cannot fit;
Phase 2 order holds inside each half. The exercise finishes and the
project still gets everything left. When everything fits, or nothing
does, the order is exactly the Phase 2 order, as before. Between
different due dates nothing changes: an earlier deadline is served
first even when it cannot be finished and a later one could be. That
trade is a separate policy decision, deliberately not made here.

Rules settled in the Phase 3 review:
  - Work is never placed after its due date. A slot on the due date
    itself is fine: due dates are whole days, not times.
  - An assignment that needs more time than exists before its due
    date gets whatever does exist and the rest is flagged.
  - Overdue work is placed as early as possible with no date limit.
  - A bigger-than-any-slot assignment is split across blocks and days.
  - Breaks go only between two chunks of work in the same block, are
    never shortened, and are never left dangling at the end of a day.
  - A chunk placed after a break is at least as long as the break
    (v1.1). The scheduler does not pay a 15-minute break for a
    1-to-14-minute session; such a tail stays free instead. The
    break length is the floor, not a separate minimum-session
    setting, and the first chunk in an empty block is not subject to
    it. With break_minutes=0 chunks sit back to back and no Break
    entry is written.
  - Within one due date, work that can still be finished is placed
    before work that cannot (v1.1). Between due dates, EDF holds.

Limitations (deliberate, for a first version):
  - Greedy fills the earliest eligible block completely before moving
    on, so work is front-loaded rather than spread evenly over the
    days before a deadline. Three hours due Tuesday become two hours
    Monday and one Tuesday, not ninety minutes each day.
  - The EDF guarantee ignores breaks, so a set of assignments that
    fits exactly can still lose a few minutes to a break and end up
    with a small remainder flagged. A tail shorter than two breaks
    in a block that already holds work is left idle rather than
    turned into a tiny session; those minutes are not recovered.
  - There is no cap on hours per day and no preference for variety,
    so a long block can be one subject end to end.
  - "Optimal" is not defined yet. Once StudyFlow decides what a
    better schedule means (fewer late hours? more even days? fewer
    context switches?), a search or optimisation pass can replace the
    greedy fill. Until then, greedy is the honest choice.
"""

from dataclasses import dataclass, field
from itertools import groupby
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
    return sorted(ranked, key=lambda a: _effective_due(a, today))


def _can_schedule_on(assignment: Assignment, study_date: date) -> bool:
    """
    The deadline rule: an assignment may only be scheduled in a study
    period that falls on or before its due date.

        Assignment due Monday
        Sunday  -> True
        Monday  -> True
        Tuesday -> False

    Dates only, no time of day: a due date is a whole day, so a study
    period on the due date itself is allowed.
    """
    return study_date <= assignment.due_date


def _effective_due(assignment: Assignment, today: date) -> date:
    """The day an assignment's deadline pressure applies: its due
    date, or today if that has already passed."""
    return max(assignment.due_date, today)


def _free_minutes_before(assignment: Assignment, blocks: List[_WorkBlock], today: date) -> int:
    """
    Minutes still free, right now, in the blocks this assignment may
    use: those on or before its due date, or every block if it is
    overdue (the same eligibility _place() applies). Read from the
    live blocks, so time already given to earlier assignments is
    not counted.
    """
    overdue = assignment.due_date < today
    return sum(
        block.remaining
        for block in blocks
        if overdue or _can_schedule_on(assignment, block.date)
    )


def _achievable_first(group: List[Assignment], blocks: List[_WorkBlock], today: date) -> List[Assignment]:
    """
    Order one due-date group: assignments whose whole estimate fits in
    the minutes currently free before their deadline, then the rest.
    The sort is stable, so the Phase 2 order the group arrived in
    survives inside each half. Breaks are not counted, in line with
    the EDF guarantee elsewhere in this module.
    """
    def cannot_finish(assignment: Assignment) -> bool:
        needed = round(assignment.estimated_hours * 60)
        return needed > _free_minutes_before(assignment, blocks, today)

    return sorted(group, key=cannot_finish)


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
    # An assignment that is already overdue has no deadline left to
    # respect: the best that can happen is finishing it as soon as
    # possible, so every block is fair game for it.
    overdue = assignment.due_date < today

    for block in blocks:
        if remaining <= 0:
            break
        if not overdue and not _can_schedule_on(assignment, block.date):
            continue   # this study period is after the due date: skip it
        free = block.remaining
        if free <= 0:
            continue

        if block.has_work:
            # A break separates this chunk from the previous one, and
            # the chunk after it must be at least as long as the break:
            # a full break is never paid for a shorter session. If the
            # block has no room for both, skip it (v1.1). With no break
            # configured, one minute of room is enough and no Break
            # entry is written.
            if free - break_minutes < max(break_minutes, 1):
                continue
            if break_minutes > 0:
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

    See the module docstring for the algorithm. Assignments are
    placed earliest deadline first; within one deadline, those that
    can still be finished go before those that cannot. Assignments
    that do not fit on or before their due date end up in
    result.unscheduled, along with how many hours were left over.
    """
    today = today or date.today()
    blocks = _generate_week_blocks(time_slots, today, days_ahead)
    result = ScheduleResult()

    ordered = _placement_order(assignments, today)
    for _, group in groupby(ordered, key=lambda a: _effective_due(a, today)):
        for assignment in _achievable_first(list(group), blocks, today):
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


def format_timetable(result: ScheduleResult, day_format: str = "%A %Y-%m-%d") -> str:
    """Render just the day-by-day blocks, one heading per day."""
    lines: List[str] = []
    for day in sorted(result.by_date):
        lines.append(day.strftime(day_format))
        for b in result.by_date[day]:
            lines.append(f"  {b.format_time_range()}  {b.label}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_schedule(result: ScheduleResult) -> str:
    """Render a ScheduleResult as readable text: the timetable, then
    whatever could not be fitted."""
    lines: List[str] = []
    timetable = format_timetable(result)
    if timetable:
        lines.extend([timetable, ""])

    if result.unscheduled:
        lines.append("Could not fit on or before the due date:")
        for assignment, hours_left in result.unscheduled:
            lines.append(
                f"  - {assignment.name}: {hours_left:.2f}h unscheduled "
                f"(due {assignment.due_date.isoformat()})"
            )

    return "\n".join(lines).rstrip()
