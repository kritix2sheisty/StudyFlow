"""
tests/test_schedule_builder.py
Pytest suite for schedule_builder.build_schedule().

Part 1 is the original basics. Part 2 covers the situations raised in
the Phase 3 review: deadlines (never place work after its due date),
allocation that respects deadlines rather than only priority order,
and break behaviour at the edges of a slot.
"""

from datetime import date, timedelta

import pytest

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_builder import _can_schedule_on, build_schedule, format_schedule

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


def test_format_schedule_mentions_due_date_for_unscheduled_work():
    slots = [slot(Weekday.WEDNESDAY, 16, 19)]
    assignments = [task("Due Tuesday", TUESDAY, 4)]
    result = build_schedule(assignments, slots, today=MONDAY)
    text = format_schedule(result)
    assert "Due Tuesday" in text
    assert TUESDAY.isoformat() in text
