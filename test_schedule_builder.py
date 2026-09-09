"""
tests/test_schedule_builder.py
Pytest suite for schedule_builder.build_schedule().
"""

from datetime import date, timedelta

from models import Assignment, Priority, TimeSlot, Weekday
from schedule_builder import build_schedule

MONDAY = date(2026, 8, 17)  # a known Monday, for deterministic weekday math


def test_single_assignment_fits_in_one_slot():
    slots = [TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]
    assignments = [Assignment(name="Essay", subject="English", due_date=MONDAY + timedelta(days=1),
                               estimated_hours=1, priority=Priority.MEDIUM)]
    result = build_schedule(assignments, slots, today=MONDAY)
    blocks = result.by_date[MONDAY]
    assert [b.label for b in blocks] == ["Essay"]
    assert blocks[0].start_minute == 16 * 60
    assert blocks[0].end_minute == 17 * 60
    assert result.unscheduled == []


def test_break_inserted_between_two_tasks_in_same_slot():
    slots = [TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]
    assignments = [
        Assignment(name="Physics", subject="Physics", due_date=MONDAY + timedelta(days=1),
                   estimated_hours=1, priority=Priority.HIGH),
        Assignment(name="CS", subject="CS", due_date=MONDAY + timedelta(days=1),
                   estimated_hours=0.5, priority=Priority.MEDIUM),
    ]
    result = build_schedule(assignments, slots, today=MONDAY, break_minutes=15)
    labels = [b.label for b in result.by_date[MONDAY]]
    assert labels == ["Physics", "Break", "CS"]
    break_block = result.by_date[MONDAY][1]
    assert break_block.end_minute - break_block.start_minute == 15


def test_assignment_bigger_than_one_slot_splits_across_days():
    slots = [
        TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=17),   # 1 hour
        TimeSlot(weekday=Weekday.TUESDAY, start_hour=16, end_hour=18),  # 2 hours
    ]
    assignments = [Assignment(name="Big project", subject="CS", due_date=MONDAY + timedelta(days=5),
                               estimated_hours=2, priority=Priority.HIGH)]
    result = build_schedule(assignments, slots, today=MONDAY)
    monday_labels = [b.label for b in result.by_date[MONDAY]]
    tuesday_labels = [b.label for b in result.by_date[date(2026, 8, 18)]]
    assert "Big project" in monday_labels
    assert "Big project" in tuesday_labels
    assert result.unscheduled == []


def test_insufficient_time_fills_by_priority_and_flags_rest():
    slots = [TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]  # 2 hours total
    assignments = [
        Assignment(name="High priority", subject="CS", due_date=MONDAY + timedelta(days=1),
                   estimated_hours=2, priority=Priority.HIGH),
        Assignment(name="Low priority", subject="Art", due_date=MONDAY + timedelta(days=1),
                   estimated_hours=1, priority=Priority.LOW),
    ]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert [b.label for b in result.by_date[MONDAY]] == ["High priority"]
    assert len(result.unscheduled) == 1
    assert result.unscheduled[0][0].name == "Low priority"
    assert result.unscheduled[0][1] == 1.0


def test_no_time_slots_means_everything_unscheduled():
    assignments = [Assignment(name="Anything", subject="Art", due_date=MONDAY + timedelta(days=1),
                               estimated_hours=1, priority=Priority.MEDIUM)]
    result = build_schedule(assignments, [], today=MONDAY)
    assert result.by_date == {}
    assert len(result.unscheduled) == 1


def test_completed_assignment_is_never_scheduled():
    slots = [TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]
    assignments = [Assignment(name="Done", subject="Bio", due_date=MONDAY + timedelta(days=1),
                               estimated_hours=1, priority=Priority.HIGH, completed=True)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert result.by_date == {}
    assert result.unscheduled == []


def test_trailing_break_is_trimmed():
    """If a task finishes with room to spare and nothing else follows,
    there shouldn't be a dangling Break as the very last entry."""
    slots = [TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]  # 2 hours
    assignments = [Assignment(name="Short task", subject="Art", due_date=MONDAY + timedelta(days=1),
                               estimated_hours=1, priority=Priority.MEDIUM)]
    result = build_schedule(assignments, slots, today=MONDAY)
    assert result.by_date[MONDAY][-1].label != "Break"


def test_empty_assignments_produces_empty_schedule():
    slots = [TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]
    result = build_schedule([], slots, today=MONDAY)
    assert result.by_date == {}
    assert result.unscheduled == []
