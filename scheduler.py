"""
scheduler.py
Phase 2 — prioritization logic for StudyFlow.

This does NOT build a full schedule (that's Phase 3, in
schedule_builder.py, which matches assignments to actual time slots).
It answers a narrower question: "if I can only work on one thing next,
what should it be?"

=====================================================================
StudyFlow's prioritization philosophy
=====================================================================

Deadlines come first. Importance second. Size is a nudge, never a veto.

The reasoning: missing a deadline is the one outcome a scheduler must
never cause, and the schedule builder works through this list in order
anyway. Putting a small task that is due tomorrow ahead of a big task
due next week costs the big task an hour or two of lead time; putting
the big task first can cost the small one its deadline.

The formula is a weighted blend (a heuristic, not an optimum):

    score = urgency * DUE_DATE_WEIGHT
          + priority * PRIORITY_WEIGHT
          + min(hours, EFFORT_CAP_HOURS) * EFFORT_WEIGHT

The weights and the effort cap are chosen so the following hold. Each
one is pinned by a test in tests/test_scheduler.py, so changing a
weight without breaking a promise is easy to check.

  1. Completed assignments are never listed.
  2. Anything overdue or due today comes before everything else.
     Among those, priority decides, then size. How late something is
     does not matter: a week late and a day late are both "late; do
     it now".
  3. Anything due tomorrow comes before anything due later, whatever
     its priority or size. (Tomorrow scores at least 53; the best a
     two-days-out item can score is 25 + 9 + 2.5 = 36.5.)
  4. On the same due date, higher priority wins no matter the size,
     for every pair of priorities. (The whole effort term is worth at
     most 2.5 points; one priority step is worth 3.)
  5. On the same due date and priority, the bigger task goes first,
     because it needs to be started sooner.
  6. From two days out, the blend takes over: importance and size can
     pull a task ahead of one due a day or two sooner. This is
     deliberate. A 10-hour HIGH exam prep due in four days should
     start before a 1-hour LOW worksheet due in three, because with
     two days of slack, what matters most is what would hurt to
     leave until the last day.
  7. Up to five days out, a deadline still beats any combination of
     importance and size in something due much later (urgency is
     worth 50 / days_left points; the most importance and size can
     add together is 6 + 2.5 = 8.5, and 50 / 5 > 8.5). From six days
     out, deadline pressure has faded and importance and size decide.
     A HIGH 5-hour project due next term outranks a LOW 1-hour
     worksheet due in a month. Both are far away; the one worth
     starting early is the big important one.

Rejected alternatives:
  - Strict lexicographic sort (due date, then priority, then size).
    Simplest to explain, but it lets a pile of low-priority busywork
    due a day sooner push a large, important task out of the week
    entirely when time is short.
  - Uncapped effort (the original Phase 2 formula). Raw hours could
    outweigh a deadline: a 40-hour project due in five days outranked
    a 1-hour task due tomorrow, and a 20-hour LOW task beat a 1-hour
    HIGH task with the same due date. The cap fixes both.
  - Effort weight 1.0 with a 5-hour cap (the first capped version).
    The effort term could reach 5 points, more than the 3-point step
    between adjacent priorities, so on the same due date a MEDIUM
    5-hour task still beat a HIGH 0-hour task and a HIGH 1-hour task
    tied with a MEDIUM 4-hour one. Halving the weight closed that.
  - Effort as hours-per-day-remaining (hours / days_left). More
    principled as a "pressure" measure, but it made big far-off tasks
    routinely jump ahead of small near ones, which is the opposite of
    the philosophy above.
"""

from datetime import date
from typing import List, Optional

from models import Assignment

# Tunable weights — how much each factor influences the final score.
# Overdue items always sort first regardless of these; see
# prioritize_assignments below.
DUE_DATE_WEIGHT = 5.0
PRIORITY_WEIGHT = 3.0
EFFORT_WEIGHT = 0.5

# Effort stops counting beyond this many hours. Keeps a very large task
# from outranking a nearer deadline or a higher priority: the maximum
# effort contribution (EFFORT_CAP_HOURS * EFFORT_WEIGHT = 2.5) stays
# below a single priority step (PRIORITY_WEIGHT = 3).
EFFORT_CAP_HOURS = 5.0


def _is_overdue(assignment: Assignment, today: date) -> bool:
    return assignment.due_date <= today


def _urgency_score(assignment: Assignment, today: date) -> float:
    """
    Higher = more time pressure. Decays smoothly as the due date gets
    further away: 10 for tomorrow, 5 for two days out, 2 for five days
    out, 1 for ten. Only meaningful for non-overdue assignments; see
    _is_overdue, which is checked separately and always wins first.
    """
    days_left = (assignment.due_date - today).days
    return 10.0 / max(days_left, 1)


def _priority_score(assignment: Assignment) -> float:
    """Priority enum is already 1 (LOW) to 3 (HIGH) — use it directly."""
    return float(assignment.priority)


def _effort_score(assignment: Assignment) -> float:
    """
    Bigger tasks get a small boost, capped at EFFORT_CAP_HOURS.

    Rationale for the boost: a 10-hour assignment due in 5 days needs
    to be started sooner than a 1-hour assignment due in 5 days, even
    though their due dates are identical.

    Rationale for the cap: beyond a few hours a task is simply "big",
    and being big should never beat being due sooner or being more
    important. Negative estimates are treated as zero.
    """
    return min(max(assignment.estimated_hours, 0.0), EFFORT_CAP_HOURS)


def prioritize_assignments(
    assignments: List[Assignment],
    today: Optional[date] = None,
) -> List[Assignment]:
    """
    Return assignments sorted from most to least urgent.

    Completed assignments are excluded entirely — there's nothing to
    prioritize once something is done.

    Sorting happens in two tiers:
      1. Overdue (or due today) items always come before non-overdue
         items, no matter their priority or size. A blended numeric
         score can't guarantee this reliably (a same-day-due HIGH
         priority item can out-score a barely-overdue LOW priority
         one), so overdue status is checked as its own tier first.
      2. Within each tier, items are ranked by a weighted score
         combining urgency, priority, and (capped) effort. See the
         module docstring for what that score promises.

    The sort is stable: assignments that score identically keep the
    order they were given in.

    `today` defaults to date.today() but can be overridden, which is
    what makes this function easy to test (see tests/test_scheduler.py).
    """
    today = today or date.today()
    active = [a for a in assignments if not a.completed]

    def weighted_score(a: Assignment) -> float:
        return (
            _urgency_score(a, today) * DUE_DATE_WEIGHT
            + _priority_score(a) * PRIORITY_WEIGHT
            + _effort_score(a) * EFFORT_WEIGHT
        )

    def sort_key(a: Assignment):
        return (_is_overdue(a, today), weighted_score(a))

    return sorted(active, key=sort_key, reverse=True)
