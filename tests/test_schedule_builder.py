"""
tests/test_schedule_builder.py
Pytest suite for schedule_builder.build_schedule().

Part 1 is the original basics. Part 2 covers the situations raised in
the Phase 3 review: deadlines (never place work after its due date),
allocation that respects deadlines rather than only priority order,
and break behaviour at the edges of a slot. Part 4 is the v1.1
achievable-first rule: within one due date, work that can still be
finished is placed before work that cannot. Part 5 is the v1.1
break-aware chunk floor: a chunk placed after a break is at least as
long as the break.
"""

from datetime import date, timedelta

import pytest

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_analyzer import assignment_status
from schedule_builder import (
    BREAK_LABEL,
    ScheduledBlock,
    ScheduleResult,
    _can_schedule_on,
    build_schedule,
    format_schedule,
)

MONDAY = date(2026, 8, 17)  # a known Monday, for deterministic weekday math
TUESDAY = MONDAY + timedelta(days=1)
WEDNESDAY = MONDAY + timedelta(days=2)
THURSDAY = MONDAY + timedelta(days=3)
FRIDAY = MONDAY + timedelta(days=4)


def slot(weekday: Weekday, start_hour: int, end_hour: int) -> TimeSlot:
    return TimeSlot(weekday=weekday, start_hour=start_hour, end_hour=end_hour)


def task(name: str, due: date, hours: float,
         priority: Priority = Priority.MEDIUM, completed: bool = False) -> Assignment:
    return Assignment(name=name, subject=name, due_date=due, estimated_hours=hours,
                      priority=priority, completed=completed)


def labels(result, day: date) -> list:
    return [b.label for b in result.by_date.get(day, [])]


def minutes_of(result, day: date, label: str) -> int:
    """Total minutes scheduled under `label` on `day`."""
    return sum(b.end_minute - b.start_minute
               for b in result.by_date.get(day, []) if b.label == label)


def assert_no_overlaps(result: ScheduleResult) -> None:
    """
    Schedule validity: on every day, once blocks are sorted by start
    time, each block must start no earlier than the previous one ends.
    Breaks count as blocks too; a break overlapping work is as wrong
    as two assignments overlapping. Raises AssertionError with the
    day and the two offending blocks otherwise.
    """
    for day, blocks in result.by_date.items():
        ordered = sorted(blocks, key=lambda b: b.start_minute)
        for current, nxt in zip(ordered, ordered[1:]):
            assert nxt.start_minute >= current.end_minute, (
                f"{day}: {current.label} {current.format_time_range()} overlaps "
                f"{nxt.label} {nxt.format_time_range()}"
            )


# =====================================================================
# Part 1 — basics
# =====================================================================

def test_single_assignment_fits_in_one_slot():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Essay", TUESDAY, 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    blocks = result.by_date[MONDAY]
    assert [b.label for b in blocks] == ["Essay"]
    assert blocks[0].start_minute == 16 * 60
    assert blocks[0].end_minute == 17 * 60
    assert result.unscheduled == []


def test_break_inserted_between_two_tasks_in_same_slot():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [
        task("Physics", TUESDAY, 1, Priority.HIGH),
        task("CS", TUESDAY, 0.5, Priority.MEDIUM),
    ]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=15)
    assert labels(result, MONDAY) == ["Physics", "Break", "CS"]
    assert_no_overlaps(result)
    break_block = result.by_date[MONDAY][1]
    assert break_block.end_minute - break_block.start_minute == 15


def test_assignment_bigger_than_one_slot_splits_across_days():
    slots = [
        slot(Weekday.MONDAY, 16, 17),   # 1 hour
        slot(Weekday.TUESDAY, 16, 18),  # 2 hours
    ]
    assignments = [task("Big project", MONDAY + timedelta(days=5), 2, Priority.HIGH)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert "Big project" in labels(result, MONDAY)
    assert "Big project" in labels(result, TUESDAY)
    assert result.unscheduled == []


def test_insufficient_time_fills_by_priority_and_flags_rest():
    slots = [slot(Weekday.MONDAY, 16, 18)]  # 2 hours total
    assignments = [
        task("High priority", TUESDAY, 2, Priority.HIGH),
        task("Low priority", TUESDAY, 1, Priority.LOW),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["High priority"]
    assert len(result.unscheduled) == 1
    assert result.unscheduled[0][0].name == "Low priority"
    assert result.unscheduled[0][1] == 1.0


def test_no_time_slots_means_everything_unscheduled():
    assignments = [task("Anything", TUESDAY, 1)]
    result = build_schedule(assignments, [], today=MONDAY)
    assert result.by_date == {}
    assert len(result.unscheduled) == 1


def test_completed_assignment_is_never_scheduled():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Done", TUESDAY, 1, Priority.HIGH, completed=True)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert result.by_date == {}
    assert result.unscheduled == []


def test_trailing_break_is_trimmed():
    """If a task finishes with room to spare and nothing else follows,
    there shouldn't be a dangling Break as the very last entry."""
    slots = [slot(Weekday.MONDAY, 16, 18)]  # 2 hours
    assignments = [task("Short task", TUESDAY, 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert result.by_date[MONDAY][-1].label != "Break"


def test_empty_assignments_produces_empty_schedule():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    result = build_schedule([], slots, today=MONDAY)
    assert result.by_date == {}
    assert result.unscheduled == []


# =====================================================================
# Part 2 — the deadline rule (Phase 3.1)
# =====================================================================
#
# The helper is tested on its own first, so the rule is proven before
# it is wired into the scheduling loop.

def test_can_schedule_before_deadline():
    due_monday = task("Due Monday", MONDAY, 1)
    sunday = MONDAY - timedelta(days=1)
    assert _can_schedule_on(due_monday, sunday) is True


def test_can_schedule_on_deadline():
    due_monday = task("Due Monday", MONDAY, 1)
    assert _can_schedule_on(due_monday, MONDAY) is True


def test_cannot_schedule_after_deadline():
    due_monday = task("Due Monday", MONDAY, 1)
    assert _can_schedule_on(due_monday, TUESDAY) is False


@pytest.mark.parametrize("offset,allowed", [
    (0, True),    # Monday
    (1, True),    # Tuesday
    (2, True),    # Wednesday
    (3, True),    # Thursday
    (4, True),    # Friday, the due date itself
    (5, False),   # Saturday
    (6, False),   # Sunday
])
def test_assignment_due_friday_can_use_monday_through_friday_only(offset, allowed):
    due_friday = task("Due Friday", FRIDAY, 1)
    assert _can_schedule_on(due_friday, MONDAY + timedelta(days=offset)) is allowed


# =====================================================================
# Part 2 — deadlines in the schedule
# =====================================================================

def test_work_is_never_scheduled_after_its_due_date():
    """
    The deadline problem. Today is Monday, the assignment is due
    Tuesday, and the only free time is Wednesday. Scheduling it on
    Wednesday would be scheduling it late, so it must stay unscheduled.
    """
    slots = [slot(Weekday.WEDNESDAY, 16, 19)]
    assignments = [task("Due Tuesday", TUESDAY, 4)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert result.by_date == {}
    assert result.unscheduled == [(assignments[0], 4.0)]


def test_build_schedule_respects_the_deadline_rule():
    """
    The integration test for _can_schedule_on. The unit tests prove
    the helper classifies dates correctly; this proves build_schedule
    actually obeys it. Physics is due Tuesday, with 1-hour slots
    Monday to Wednesday: Monday and Tuesday get Physics, Wednesday
    must not.

    Physics needs 3 hours, not the 2 in the brief. With 2 hours the
    work fits before the deadline and Wednesday is never reached, so
    the test would pass even with the rule switched off. With 3, the
    third hour is exactly what the rule has to refuse.
    """
    slots = [slot(d, 16, 17) for d in (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY)]
    assignments = [task("Physics", TUESDAY, 3)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["Physics"]
    assert labels(result, TUESDAY) == ["Physics"]
    assert "Physics" not in labels(result, WEDNESDAY)
    assert result.unscheduled == [(assignments[0], 1.0)]


def test_physics_lab_due_tuesday_recognises_wednesday_is_too_late():
    """
    The Phase 3.1 example. Physics Lab is due Tuesday and needs 3
    hours, with 2-hour slots Monday to Wednesday. The third hour must
    not spill onto Wednesday: Wednesday is too late.
    """
    slots = [slot(d, 16, 18) for d in (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY)]
    assignments = [task("Physics Lab", TUESDAY, 3)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert minutes_of(result, MONDAY, "Physics Lab") == 120
    assert minutes_of(result, TUESDAY, "Physics Lab") == 60
    assert "Physics Lab" not in labels(result, WEDNESDAY)
    assert result.unscheduled == []


def test_work_may_be_scheduled_on_the_due_date_itself():
    """Due dates are whole days, so a slot on the due date still counts."""
    slots = [slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Due Tuesday", TUESDAY, 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, TUESDAY) == ["Due Tuesday"]
    assert result.unscheduled == []


def test_work_short_of_its_deadline_is_partly_scheduled_and_rest_flagged():
    """Due Tuesday, 5 hours, only 2 hours free before then: 3 hours flagged."""
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.WEDNESDAY, 16, 19)]
    assignments = [task("Due Tuesday", TUESDAY, 5)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert minutes_of(result, MONDAY, "Due Tuesday") == 120
    assert WEDNESDAY not in result.by_date
    assert result.unscheduled == [(assignments[0], 3.0)]


def test_five_hours_due_friday_with_four_free_splits_and_flags_one_hour():
    """
    The Phase 3.1 complication. Due Friday, needs 5 hours; only
    Thursday and Friday 4-6 PM are free. The scheduler splits it
    2 + 2 and reports the missing hour, building on the existing
    unscheduled report rather than inventing a new one.
    """
    slots = [slot(Weekday.THURSDAY, 16, 18), slot(Weekday.FRIDAY, 16, 18)]
    assignments = [task("Due Friday", FRIDAY, 5)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert minutes_of(result, THURSDAY, "Due Friday") == 120
    assert minutes_of(result, FRIDAY, "Due Friday") == 120
    assert result.unscheduled == [(assignments[0], 1.0)]


def test_overdue_work_is_scheduled_as_soon_as_possible():
    """A missed deadline is not a reason to never schedule the work."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Was due last week", MONDAY - timedelta(days=7), 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["Was due last week"]
    assert result.unscheduled == []


def test_due_today_uses_only_today():
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Due today", MONDAY, 3)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert minutes_of(result, MONDAY, "Due today") == 120
    assert TUESDAY not in result.by_date
    assert result.unscheduled == [(assignments[0], 1.0)]


# =====================================================================
# Part 2 — deadline-aware allocation
# =====================================================================

def test_review_example_physics_finishes_before_tuesday_and_cs_takes_wednesday():
    """
    The example from the Phase 3 review. Physics is due Tuesday and
    needs 3 hours; CS is due Friday and needs 3 hours; 2-hour slots
    Monday to Wednesday. All of Physics must land on Monday and
    Tuesday, and Wednesday belongs to CS.
    """
    slots = [slot(d, 16, 18) for d in (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY)]
    assignments = [
        task("Physics", TUESDAY, 3, Priority.MEDIUM),
        task("CS", FRIDAY, 3, Priority.MEDIUM),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    physics_total = sum(minutes_of(result, d, "Physics") for d in (MONDAY, TUESDAY))
    assert physics_total == 180
    assert "Physics" not in labels(result, WEDNESDAY)
    assert "CS" in labels(result, WEDNESDAY)
    assert not any(a.name == "Physics" for a, _ in result.unscheduled)
    assert_no_overlaps(result)


def test_earlier_deadline_gets_time_even_when_a_bigger_task_outranks_it():
    """
    The greedy trap. Phase 2 ranks the 10-hour HIGH exam prep (due
    Friday, four days out) above the 1-hour LOW worksheet (due
    Thursday, three days out); that is promise 6 of the prioritizer.
    Filling blocks in that order lets exam prep eat Monday to Friday
    and leaves the worksheet with no time before its deadline, even
    though an hour for it was trivially available.
    """
    slots = [slot(d, 16, 18) for d in
             (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY)]
    assignments = [
        task("Exam prep", FRIDAY, 10, Priority.HIGH),
        task("Worksheet", THURSDAY, 1, Priority.LOW),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    worksheet_total = sum(minutes_of(result, d, "Worksheet")
                          for d in (MONDAY, TUESDAY, WEDNESDAY, THURSDAY))
    assert worksheet_total == 60
    assert not any(a.name == "Worksheet" for a, _ in result.unscheduled)
    # Exam prep still gets everything that is left.
    assert any(a.name == "Exam prep" for a, _ in result.unscheduled)
    assert_no_overlaps(result)


def test_earlier_deadline_is_protected():
    """
    Phase 3.2: does "highest priority first" always produce the best
    schedule? The scenario from the brief, shifted two days later.

    Physics is HIGH and needs 5 hours; Math is MEDIUM and needs 2.
    Math is due a day before Physics. Only 6 hours of study time
    exist, so the two cannot both finish: 7 hours are needed.

    Why shifted: with Math due tomorrow and Physics the day after,
    the prioritizer already ranks Math first (nothing outranks a
    task due tomorrow), so the test would not exercise the danger.
    With Math due Thursday and Physics Friday, the prioritizer ranks
    Physics first (24.0 to 23.7), which is exactly the ordering that
    would let Physics take Monday to Wednesday and leave Math 1.25
    hours short of its deadline.

    The protection is that placement orders by deadline, not by that
    rank: Math gets Monday and finishes; Physics gets the rest and
    the hour that does not fit is reported against Physics.
    """
    slots = [slot(d, 16, 18) for d in (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY)]
    physics = task("Physics", FRIDAY, 5, Priority.HIGH)
    math = task("Math", THURSDAY, 2, Priority.MEDIUM)
    result = build_schedule([physics, math], slots, today=MONDAY)

    # Math is fully scheduled before its deadline.
    math_total = sum(minutes_of(result, d, "Math") for d in (MONDAY, TUESDAY, WEDNESDAY))
    assert math_total == 120
    assert not any(a.name == "Math" for a, _ in result.unscheduled)

    # The shortfall lands on Physics, the one with time to spare.
    assert result.unscheduled == [(physics, 1.0)]
    assert_no_overlaps(result)


def test_same_deadline_falls_back_to_phase_2_order():
    """With equal deadlines and not enough time, priority decides who is cut."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [
        task("Low", TUESDAY, 2, Priority.LOW),
        task("High", TUESDAY, 2, Priority.HIGH),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["High"]
    assert [a.name for a, _ in result.unscheduled] == ["Low"]


def test_later_task_fills_leftover_room_in_an_earlier_block():
    """
    A task processed later may still use free minutes left in an
    earlier block, so leftover time is not wasted just because a
    tighter deadline was handled first.
    """
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [
        task("Due Monday", MONDAY, 1),
        task("Due Tuesday", TUESDAY, 1),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["Due Monday", "Break", "Due Tuesday"]
    assert result.unscheduled == []
    assert_no_overlaps(result)


# =====================================================================
# Part 2 — break behaviour
# =====================================================================

def test_assignment_that_exactly_fills_a_slot_gets_no_break():
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Two hours", TUESDAY, 2)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["Two hours"]
    assert result.by_date[MONDAY][0].end_minute == 18 * 60


def test_two_one_hour_tasks_in_a_two_hour_slot_share_a_break():
    """1h + 15 min break + 45 min: the second task loses 15 minutes to the break."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [
        task("First", TUESDAY, 1, Priority.HIGH),
        task("Second", TUESDAY, 1, Priority.LOW),
    ]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=15)
    assert labels(result, MONDAY) == ["First", "Break", "Second"]
    assert minutes_of(result, MONDAY, "Second") == 45
    assert result.unscheduled == [(assignments[1], 0.25)]
    assert_no_overlaps(result)


def test_task_bigger_than_its_slot_fills_it_with_no_break():
    """
    The 'small slot, big task' case. TimeSlots are whole hours, so the
    smallest slot is 1 hour; a 1.5-hour task fills it exactly, gets no
    break (there is nothing to break before), and the rest is flagged.
    """
    slots = [slot(Weekday.MONDAY, 16, 17)]
    assignments = [task("Ninety minutes", TUESDAY, 1.5)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert labels(result, MONDAY) == ["Ninety minutes"]
    assert minutes_of(result, MONDAY, "Ninety minutes") == 60
    assert result.unscheduled == [(assignments[0], 0.5)]


def test_break_is_never_the_last_entry_of_a_day():
    slots = [slot(Weekday.MONDAY, 16, 18), slot(Weekday.TUESDAY, 16, 18)]
    assignments = [task("Due Monday", MONDAY, 1), task("Due Tuesday", TUESDAY, 1)]
    result = build_schedule(assignments, slots, today=MONDAY)
    for day, blocks in result.by_date.items():
        assert blocks[-1].label != "Break", f"dangling break on {day}"


def test_break_that_leaves_no_room_for_work_is_not_inserted():
    """
    A 1h45 task in a 2h slot leaves 15 minutes. A full 15-minute break
    would use all of it, so there is no point placing a second chunk
    there: the break is not inserted, the 15 minutes stay free, and the
    tail is flagged. Breaks are never shortened to squeeze work in.
    """
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [task("Long", TUESDAY, 1.75), task("Tail", TUESDAY, 0.25)]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=15)
    assert labels(result, MONDAY) == ["Long"]
    assert result.unscheduled == [(assignments[1], 0.25)]


# =====================================================================
# Part 3 — schedule validity
# =====================================================================

def test_scheduled_blocks_do_not_overlap():
    """
    Three 2-hour assignments compete for one 2-hour slot. At most two
    hours of work may be scheduled, and no two blocks may overlap.
    """
    slots = [slot(Weekday.MONDAY, 16, 18)]
    assignments = [
        task("Math", TUESDAY, 2, Priority.MEDIUM),
        task("Physics", TUESDAY, 2, Priority.HIGH),
        task("CS", TUESDAY, 2, Priority.LOW),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert_no_overlaps(result)

    total_work = sum(b.end_minute - b.start_minute
                     for b in result.by_date[MONDAY] if b.label != "Break")
    assert total_work <= 120
    # Only one of the three fits; the other two are reported in full.
    assert labels(result, MONDAY) == ["Physics"]
    assert sorted(a.name for a, _ in result.unscheduled) == ["CS", "Math"]
    assert all(hours == 2.0 for _, hours in result.unscheduled)


def test_no_overlaps_across_a_crowded_week():
    """
    Many assignments, mixed deadlines, two slots on some days, and
    later tasks back-filling leftover room in earlier blocks. Every
    day must still be a clean sequence of non-overlapping blocks.
    """
    slots = [
        slot(Weekday.MONDAY, 8, 9), slot(Weekday.MONDAY, 16, 18),
        slot(Weekday.TUESDAY, 16, 18),
        slot(Weekday.WEDNESDAY, 8, 9), slot(Weekday.WEDNESDAY, 16, 17),
        slot(Weekday.THURSDAY, 16, 18),
    ]
    assignments = [
        task("Overdue", MONDAY - timedelta(days=1), 0.5, Priority.LOW),
        task("Due today", MONDAY, 1.5, Priority.MEDIUM),
        task("Math", TUESDAY, 2, Priority.MEDIUM),
        task("Physics", WEDNESDAY, 2.25, Priority.HIGH),
        task("CS", THURSDAY, 3, Priority.HIGH),
        task("Essay", FRIDAY, 1, Priority.LOW),
        task("Done", TUESDAY, 5, Priority.HIGH, completed=True),
    ]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=10)
    assert_no_overlaps(result)
    assert "Done" not in {b.label for blocks in result.by_date.values() for b in blocks}


def test_assert_no_overlaps_catches_an_overlap():
    """The helper must fail on the exact schedule the brief forbids."""
    bad = ScheduleResult(by_date={MONDAY: [
        ScheduledBlock(16 * 60, 17 * 60, "Math"),
        ScheduledBlock(16 * 60, 18 * 60, "Physics"),
    ]})
    with pytest.raises(AssertionError, match="Math .* overlaps Physics"):
        assert_no_overlaps(bad)


def test_assert_no_overlaps_accepts_touching_blocks():
    """A block that starts exactly when the previous one ends is fine."""
    ok = ScheduleResult(by_date={MONDAY: [
        ScheduledBlock(17 * 60, 18 * 60, "Physics"),   # deliberately out of order
        ScheduledBlock(16 * 60, 17 * 60, "Math"),
    ]})
    assert_no_overlaps(ok)


def test_format_schedule_mentions_due_date_for_unscheduled_work():
    slots = [slot(Weekday.WEDNESDAY, 16, 19)]
    assignments = [task("Due Tuesday", TUESDAY, 4)]
    result = build_schedule(assignments, slots, today=MONDAY)
    text = format_schedule(result)
    assert "Due Tuesday" in text
    assert TUESDAY.isoformat() in text


# =====================================================================
# Part 4 — achievable first (v1.1)
# =====================================================================
#
# Two tasks with the same due date compete for the same hours. If one
# of them cannot be finished in the time that is free before that date
# anyway, it should not take hours that would have completed the other.
# Between different due dates nothing changes: earliest deadline first.

SIX_HOURS = [slot(Weekday.MONDAY, 15, 18), slot(Weekday.TUESDAY, 15, 18)]


def status_of(result, assignment) -> str:
    return assignment_status(result, assignment)


def unscheduled_of(result) -> dict:
    return {a.name: hours for a, hours in result.unscheduled}


def test_impossible_task_does_not_starve_an_achievable_one_with_the_same_deadline():
    """
    The brief's example. Monday and Tuesday 3-6 PM (6h); CS Project
    20h and Pure Math 2h, both HIGH, both due Wednesday. Phase 2
    ranks CS first (same date and priority, bigger task first), and
    on its own that lets CS take all six hours.

    Pure Math can be finished, CS cannot, so Pure Math goes first and
    CS gets everything left: Monday 5:15-6 after the break, and all
    of Tuesday, 3h45 in total.
    """
    cs = task("CS Project", WEDNESDAY, 20, Priority.HIGH)
    math = task("Pure Math", WEDNESDAY, 2, Priority.HIGH)
    result = build_schedule([cs, math], SIX_HOURS, today=MONDAY)

    assert minutes_of(result, MONDAY, "Pure Math") == 120
    assert status_of(result, math) == "COMPLETE"
    assert minutes_of(result, MONDAY, "CS Project") == 45
    assert minutes_of(result, TUESDAY, "CS Project") == 180
    assert status_of(result, cs) == "PARTIAL"
    assert unscheduled_of(result) == {"CS Project": 16.25}

    # The timetable itself, as the brief drew it.
    assert [(b.format_time_range(), b.label) for b in result.by_date[MONDAY]] == [
        ("3 PM–5 PM", "Pure Math"),
        ("5 PM–5:15 PM", "Break"),
        ("5:15 PM–6 PM", "CS Project"),
    ]
    assert [(b.format_time_range(), b.label) for b in result.by_date[TUESDAY]] == [
        ("3 PM–6 PM", "CS Project"),
    ]
    assert_no_overlaps(result)


def test_achievable_first_ignores_priority_within_a_deadline():
    """A LOW task that can be finished still goes before a HIGH task that cannot."""
    cs = task("CS Project", WEDNESDAY, 20, Priority.HIGH)
    math = task("Pure Math", WEDNESDAY, 2, Priority.LOW)
    result = build_schedule([cs, math], SIX_HOURS, today=MONDAY)

    assert minutes_of(result, MONDAY, "Pure Math") == 120
    assert status_of(result, math) == "COMPLETE"
    assert minutes_of(result, MONDAY, "CS Project") + minutes_of(result, TUESDAY, "CS Project") == 225
    assert unscheduled_of(result) == {"CS Project": 16.25}
    assert_no_overlaps(result)


def test_two_impossible_tasks_still_fall_back_to_phase_2_order():
    """
    CS 20h HIGH and Math 8h MEDIUM in 6h: neither can be finished, so
    nothing is protected and the Phase 2 rank decides, as before. CS
    (higher priority) takes all six hours; Math gets nothing.
    """
    cs = task("CS Project", WEDNESDAY, 20, Priority.HIGH)
    math = task("Pure Math", WEDNESDAY, 8, Priority.MEDIUM)
    result = build_schedule([cs, math], SIX_HOURS, today=MONDAY)

    assert labels(result, MONDAY) == ["CS Project"]
    assert labels(result, TUESDAY) == ["CS Project"]
    assert status_of(result, math) == "UNSCHEDULED"
    assert unscheduled_of(result) == {"CS Project": 14.0, "Pure Math": 8.0}
    assert_no_overlaps(result)


def test_task_that_fits_exactly_is_still_placed_first():
    """
    CS 6h fits the six hours exactly, so it is achievable and keeps
    its Phase 2 place ahead of Math 2h. CS finishes; Math, with no
    time left, is unscheduled. Same as before the change.
    """
    cs = task("CS Project", WEDNESDAY, 6, Priority.HIGH)
    math = task("Pure Math", WEDNESDAY, 2, Priority.HIGH)
    result = build_schedule([cs, math], SIX_HOURS, today=MONDAY)

    assert labels(result, MONDAY) == ["CS Project"]
    assert labels(result, TUESDAY) == ["CS Project"]
    assert status_of(result, cs) == "COMPLETE"
    assert status_of(result, math) == "UNSCHEDULED"
    assert unscheduled_of(result) == {"Pure Math": 2.0}
    assert_no_overlaps(result)


def test_three_way_same_deadline():
    """
    CS 20h HIGH, Math 2h HIGH, Chemistry 3h LOW, all due Wednesday,
    6h available. Math and Chemistry can both be finished (Phase 2
    order among them: Math, then Chemistry); CS cannot and comes
    last, getting the 30 minutes left on Tuesday after the break.
    """
    cs = task("CS Project", WEDNESDAY, 20, Priority.HIGH)
    math = task("Pure Math", WEDNESDAY, 2, Priority.HIGH)
    chem = task("Chemistry", WEDNESDAY, 3, Priority.LOW)
    result = build_schedule([cs, math, chem], SIX_HOURS, today=MONDAY)

    assert status_of(result, math) == "COMPLETE"
    assert status_of(result, chem) == "COMPLETE"
    assert status_of(result, cs) == "PARTIAL"
    assert labels(result, MONDAY) == ["Pure Math", "Break", "Chemistry"]
    assert labels(result, TUESDAY) == ["Chemistry", "Break", "CS Project"]
    assert minutes_of(result, TUESDAY, "CS Project") == 30
    assert unscheduled_of(result) == {"CS Project": 19.5}
    assert_no_overlaps(result)


def test_earlier_deadline_still_beats_an_achievable_later_one():
    """
    EDF is unchanged. CS 20h is due Tuesday and cannot be finished;
    Pure Math 2h is due Wednesday and could be. Only Monday and
    Tuesday exist. The earlier deadline is still served first, so CS
    takes both days and Pure Math is left out. Letting a later
    deadline jump ahead is a separate policy decision, deliberately
    not made here.
    """
    cs = task("CS Project", TUESDAY, 20, Priority.HIGH)
    math = task("Pure Math", WEDNESDAY, 2, Priority.HIGH)
    result = build_schedule([cs, math], SIX_HOURS, today=MONDAY)

    assert labels(result, MONDAY) == ["CS Project"]
    assert labels(result, TUESDAY) == ["CS Project"]
    assert status_of(result, math) == "UNSCHEDULED"
    assert unscheduled_of(result) == {"CS Project": 14.0, "Pure Math": 2.0}
    assert_no_overlaps(result)


def test_overdue_impossible_task_does_not_starve_work_due_today():
    """
    An overdue task and a task due today share the "today" group.
    The overdue essay (20h, HIGH) outranks the quiz prep (1h, MEDIUM)
    in Phase 2 and may use any block, but it cannot be finished in
    the two hours that exist; the quiz prep can. Quiz prep goes
    first and finishes; the essay gets the 45 minutes after the break.
    """
    slots = [slot(Weekday.MONDAY, 16, 18)]
    essay = task("Late essay", MONDAY - timedelta(days=7), 20, Priority.HIGH)
    quiz = task("Quiz prep", MONDAY, 1, Priority.MEDIUM)
    result = build_schedule([essay, quiz], slots, today=MONDAY)

    assert labels(result, MONDAY) == ["Quiz prep", "Break", "Late essay"]
    assert minutes_of(result, MONDAY, "Quiz prep") == 60
    assert status_of(result, quiz) == "COMPLETE"
    assert minutes_of(result, MONDAY, "Late essay") == 45
    assert unscheduled_of(result) == {"Late essay": 19.25}
    assert_no_overlaps(result)


# =====================================================================
# Part 5 — break-aware chunk floor (v1.1)
# =====================================================================
#
# A block that already holds work is reused only if it has room for
# the break plus at least a break's worth of study after it. A full
# 15-minute break is never paid for a 1-to-14-minute session. The
# floor uses the break length itself; there is no separate minimum
# session setting, and the first chunk in an empty block is not
# subject to it.

def assert_no_short_session_after_a_break(result: ScheduleResult, break_minutes: int) -> None:
    for day, blocks in result.by_date.items():
        for previous, current in zip(blocks, blocks[1:]):
            if previous.label == BREAK_LABEL:
                length = current.end_minute - current.start_minute
                assert length >= break_minutes, (
                    f"{day}: {length}-minute {current.label} session after a break"
                )


def test_a_chunk_after_a_break_is_at_least_as_long_as_the_break():
    """
    Long 1h44 leaves 16 minutes of a 2h block. Before the floor that
    became a 15-minute break and a 1-minute Tail session. Now the
    block is not reused: no break, the 16 minutes stay idle, and the
    whole of Tail is flagged.
    """
    slots = [slot(Weekday.MONDAY, 16, 18)]
    long_task = task("Long", TUESDAY, 104 / 60, Priority.HIGH)
    tail = task("Tail", TUESDAY, 0.25)
    result = build_schedule([long_task, tail], slots, today=MONDAY, break_minutes=15)

    assert labels(result, MONDAY) == ["Long"]
    assert minutes_of(result, MONDAY, "Long") == 104
    assert minutes_of(result, MONDAY, "Tail") == 0
    assert result.by_date[MONDAY][-1].end_minute == 18 * 60 - 16      # 16 idle minutes
    assert result.unscheduled == [(tail, 0.25)]
    assert_no_short_session_after_a_break(result, 15)


def test_exactly_break_plus_break_is_reused():
    """Long 1h30 leaves 30 minutes: a 15-minute break and a 15-minute Tail, exactly the floor."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    long_task = task("Long", TUESDAY, 1.5, Priority.HIGH)
    tail = task("Tail", TUESDAY, 0.25)
    result = build_schedule([long_task, tail], slots, today=MONDAY, break_minutes=15)

    assert labels(result, MONDAY) == ["Long", "Break", "Tail"]
    assert [b.end_minute - b.start_minute for b in result.by_date[MONDAY]] == [90, 15, 15]
    assert result.unscheduled == []
    assert_no_overlaps(result)


def test_after_break_floor_does_not_apply_to_the_first_chunk():
    """A 10-minute task alone in an empty 2h block is scheduled; the floor is about breaks, not sessions."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    ten_minutes = task("Ten minutes", TUESDAY, 10 / 60)
    result = build_schedule([ten_minutes], slots, today=MONDAY)

    assert labels(result, MONDAY) == ["Ten minutes"]
    assert minutes_of(result, MONDAY, "Ten minutes") == 10
    assert result.unscheduled == []


def test_zero_break_inserts_no_break_entry():
    """With break_minutes=0 two tasks sit back to back and no Break entry, zero-length or otherwise, exists."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    first = task("First", TUESDAY, 1, Priority.HIGH)
    second = task("Second", TUESDAY, 1, Priority.LOW)
    result = build_schedule([first, second], slots, today=MONDAY, break_minutes=0)

    assert labels(result, MONDAY) == ["First", "Second"]
    a, b = result.by_date[MONDAY]
    assert (a.start_minute, a.end_minute) == (16 * 60, 17 * 60)
    assert (b.start_minute, b.end_minute) == (17 * 60, 18 * 60)
    assert result.unscheduled == []
    for blocks in result.by_date.values():
        assert all(x.label != BREAK_LABEL for x in blocks)
        assert all(x.end_minute > x.start_minute for x in blocks)
    assert_no_overlaps(result)


def test_floor_scales_with_break_minutes():
    """With a 10-minute break, 19 free minutes are not reused and 20 are: break 10 plus study 10."""
    slots = [slot(Weekday.MONDAY, 16, 18)]
    tail = task("Tail", TUESDAY, 10 / 60)

    nineteen_left = task("Long", TUESDAY, 101 / 60, Priority.HIGH)
    result = build_schedule([nineteen_left, tail], slots, today=MONDAY, break_minutes=10)
    assert labels(result, MONDAY) == ["Long"]
    assert result.unscheduled == [(tail, 10 / 60)]

    twenty_left = task("Long", TUESDAY, 100 / 60, Priority.HIGH)
    result = build_schedule([twenty_left, tail], slots, today=MONDAY, break_minutes=10)
    assert labels(result, MONDAY) == ["Long", "Break", "Tail"]
    assert [b.end_minute - b.start_minute for b in result.by_date[MONDAY]] == [100, 10, 10]
    assert result.unscheduled == []
    assert_no_short_session_after_a_break(result, 10)


def test_demo_week_has_no_short_session_after_a_break():
    """
    The end-to-end demo week (weekdays 4-6 PM, Saturday 10-1,
    Sunday 2-5) with Pure Math Practice at 1h44 instead of 2h. Before
    the floor, Wednesday was Pure Math 104 minutes, a 15-minute break,
    then a 1-minute Biology Lab session. Now Wednesday ends after Pure
    Math, Biology takes all of Thursday, and no break anywhere in the
    week is followed by a session shorter than the break. Every
    assignment still finishes.

    The demo's other short chunk, the last 15 minutes of Computer
    Science on Monday, is the FIRST chunk of an otherwise empty block.
    The floor is about breaks and leaves it alone; whether a session
    may be that short at all is a separate decision.
    """
    wednesday = date(2026, 9, 9)
    slots = [slot(d, 16, 18) for d in (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY,
                                       Weekday.THURSDAY, Weekday.FRIDAY)]
    slots += [slot(Weekday.SATURDAY, 10, 13), slot(Weekday.SUNDAY, 14, 17)]
    due = lambda days: wednesday + timedelta(days=days)
    assignments = [
        task("Mathematics IA", due(4), 3, Priority.HIGH),
        task("Computer Science Project", due(6), 5, Priority.HIGH),
        task("Biology Lab", due(3), 2, Priority.MEDIUM),
        task("French Assignment", due(7), 1, Priority.LOW),
        task("Pure Math Practice", due(2), 104 / 60, Priority.HIGH),
    ]
    result = build_schedule(assignments, slots, today=wednesday, break_minutes=15)

    assert labels(result, wednesday) == ["Pure Math Practice"]
    assert minutes_of(result, wednesday, "Biology Lab") == 0
    assert minutes_of(result, wednesday + timedelta(days=1), "Biology Lab") == 120
    assert result.unscheduled == []
    assert_no_short_session_after_a_break(result, 15)
    assert_no_overlaps(result)
