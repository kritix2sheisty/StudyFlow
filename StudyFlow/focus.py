"""
StudyFlow/focus.py
The logic behind the Focus page, kept out of the State so it can be
tested on its own.

A generated plan already says what a student should be doing today
and when. The Focus page turns the block that is happening right now
into one thing on the screen: the assignment, and a countdown.

    sessions_for_today()  -> today's work blocks as Session rows
    pick()                -> which one is now, which one is next
    clock()               -> seconds as "45:00"

Nothing here schedules anything. The engine decides the blocks; this
module only reads them.
"""

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional, Tuple

from models import Assignment
from schedule_builder import BREAK_LABEL
from study_plan import StudyPlan


@dataclass
class Session:
    """One of today's study blocks, as the Focus page needs it."""
    label: str          # the assignment name
    subject: str        # its subject, "" if unknown
    time: str           # "4 PM–6 PM", as the plan shows it
    start_minute: int   # minutes since midnight
    end_minute: int

    @property
    def minutes(self) -> int:
        return self.end_minute - self.start_minute


def sessions_for_today(plan: StudyPlan, assignments: Iterable[Assignment], today: date) -> List[Session]:
    """
    Today's work blocks, in time order, with each one's subject looked
    up from the assignments. Breaks are left out: the Focus page runs
    its own break countdown after a session, using the plan's break
    length, rather than treating a scheduled break as a session.
    """
    subject_of = {a.name: a.subject for a in assignments}
    return [
        Session(label=b.label, subject=subject_of.get(b.label, ""), time=b.format_time_range(),
                start_minute=b.start_minute, end_minute=b.end_minute)
        for b in plan.schedule.by_date.get(today, [])
        if b.label != BREAK_LABEL
    ]


def pick(sessions: List[Session], now_minute: int,
         after: Optional[str] = None) -> Tuple[Optional[Session], Optional[Session]]:
    """
    (current, next) for a moment of the day.

    current: the session whose block contains `now_minute`, if any.
    next:    the first session that starts after now, or after the
             current one when there is one.

    `after` names a session the student has just finished early; it
    and everything before it are skipped, so the page moves on to
    what follows instead of showing the same block again.

        sessions 4-6 PM Math, 6:15-7 PM CS; now 4:30 PM
            -> (Math, CS)
        now 3 PM      -> (None, Math)
        now 7:30 PM   -> (None, None)
        after="Math", now 4:30 PM -> (None, CS)
    """
    if after is not None:
        names = [s.label for s in sessions]
        if after in names:
            sessions = sessions[names.index(after) + 1:]
        return None, next((s for s in sessions), None)

    current = next((s for s in sessions if s.start_minute <= now_minute < s.end_minute), None)
    if current is not None:
        later = [s for s in sessions if s.start_minute >= current.end_minute]
    else:
        later = [s for s in sessions if s.start_minute > now_minute]
    return current, (later[0] if later else None)


def clock(seconds: int) -> str:
    """Seconds as a countdown: 2700 -> '45:00', 61 -> '01:01', 3600 -> '60:00'."""
    seconds = max(int(seconds), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
