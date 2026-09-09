"""
schedule_builder.py
Phase 3 — turns a prioritized assignment list + a set of recurring
weekly time slots into an actual day-by-day, time-blocked schedule.

This is a GREEDY algorithm: it doesn't search for the "best possible"
arrangement, it just walks through assignments in priority order and
stuffs each one into the earliest available time it can find. That's
simple to reason about and fast to run, at the cost of not being
provably optimal — a reasonable trade-off for a first version.

Design decisions locked in during Phase 3 planning:
- An assignment bigger than any single slot gets SPLIT across
  multiple slots/days rather than requiring one slot big enough.
- A fixed-length BREAK is auto-inserted after each scheduled chunk,
  as long as there's room left in that slot.
- If there isn't enough total time this week for everything, the
  schedule fills what it can (respecting priority order) and reports
  the rest as unscheduled rather than shrinking estimates or
  refusing to build a partial schedule.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple

from models import Assignment, TimeSlot, Weekday
from scheduler import prioritize_assignments

DEFAULT_BREAK_MINUTES = 15
DEFAULT_DAYS_AHEAD = 7


@dataclass
class ScheduledBlock:
    """One entry on the final schedule: a chunk of time with a label."""
    start_minute: int   # minutes since midnight
    end_minute: int
    label: str           # assignment name, or "Break"

    def format_time_range(self) -> str:
        return f"{_format_minutes(self.start_minute)}\u2013{_format_minutes(self.end_minute)}"


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
        self.cursor = start_hour * 60      # minutes since midnight, moves forward as we fill
        self.remaining = (end_hour - start_hour) * 60  # minutes still free


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
    blocks.sort(key=lambda b: (b.date, b.cursor))
    return blocks


def build_schedule(
    assignments: List[Assignment],
    time_slots: List[TimeSlot],
    today: date = None,
    break_minutes: int = DEFAULT_BREAK_MINUTES,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
) -> ScheduleResult:
    """
    Greedily fill available time_slots with assignments, most urgent
    first (via prioritize_assignments), splitting any assignment that
    doesn't fit in one block and inserting a break after each chunk.

    Assignments that don't fit anywhere within `days_ahead` days end
    up in result.unscheduled, along with how many hours were left over.
    """
    today = today or date.today()
    ordered = prioritize_assignments(assignments, today=today)
    blocks = _generate_week_blocks(time_slots, today, days_ahead)

    result = ScheduleResult()
    block_index = 0

    for assignment in ordered:
        remaining_minutes = round(assignment.estimated_hours * 60)

        while remaining_minutes > 0 and block_index < len(blocks):
            block = blocks[block_index]

            if block.remaining <= 0:
                block_index += 1
                continue

            chunk = min(remaining_minutes, block.remaining)
            start = block.cursor
            end = start + chunk
            result.by_date.setdefault(block.date, []).append(
                ScheduledBlock(start, end, assignment.name)
            )
            block.cursor = end
            block.remaining -= chunk
            remaining_minutes -= chunk

            # Auto-insert a break if there's still room in this block,
            # whether this assignment is finished or needs to continue.
            if block.remaining > 0:
                break_len = min(break_minutes, block.remaining)
                b_start = block.cursor
                b_end = b_start + break_len
                result.by_date[block.date].append(
                    ScheduledBlock(b_start, b_end, "Break")
                )
                block.cursor = b_end
                block.remaining -= break_len

            if block.remaining <= 0:
                block_index += 1

        if remaining_minutes > 0:
            result.unscheduled.append((assignment, remaining_minutes / 60))

    _trim_trailing_break(result)
    return result


def _trim_trailing_break(result: ScheduleResult) -> None:
    """
    If the very last entry in the whole schedule is a Break (nothing
    ever gets scheduled after it, because we ran out of assignments),
    drop it — a break with nothing after it is just noise.
    """
    if not result.by_date:
        return
    last_date = max(result.by_date)
    day_blocks = result.by_date[last_date]
    if day_blocks and day_blocks[-1].label == "Break":
        day_blocks.pop()
        if not day_blocks:
            del result.by_date[last_date]


def format_schedule(result: ScheduleResult) -> str:
    """Render a ScheduleResult as readable text, grouped by day."""
    lines: List[str] = []
    for day in sorted(result.by_date):
        lines.append(day.strftime("%A %Y-%m-%d"))
        for b in result.by_date[day]:
            lines.append(f"  {b.format_time_range()}  {b.label}")
        lines.append("")

    if result.unscheduled:
        lines.append("Could not fit (ran out of available time):")
        for assignment, hours_left in result.unscheduled:
            lines.append(f"  - {assignment.name}: {hours_left:.2f}h unscheduled")

    return "\n".join(lines).rstrip()
