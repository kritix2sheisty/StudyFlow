"""
tests/test_study_time.py
Pytest suite for the Study Time form logic in StudyFlow/study_time.py.

The page shows "4:00 PM"; the model stores 16. These tests pin that
translation both ways, the validation the mentor asked for, and the
rows the dashboard renders.
"""

import pytest

import storage
from models import TimeSlot, Weekday
from StudyFlow.study_time import (
    END_CHOICES,
    START_CHOICES,
    WEEKDAYS,
    hour_label,
    is_valid,
    label_to_hour,
    no_errors,
    row_from_slot,
    rows_from,
    to_time_slot,
    total_hours,
    validate_form,
)


# ---------- Labels <-> 24-hour integers ----------

@pytest.mark.parametrize("hour,label", [
    (0, "12:00 AM"), (1, "1:00 AM"), (11, "11:00 AM"), (12, "12:00 PM"),
    (13, "1:00 PM"), (16, "4:00 PM"), (18, "6:00 PM"), (23, "11:00 PM"), (24, "12:00 AM"),
])
def test_hour_label(hour, label):
    assert hour_label(hour) == label


def test_labels_round_trip_to_the_same_integers():
    for hour in range(0, 24):
        assert label_to_hour(hour_label(hour)) == hour
    for hour in range(1, 25):
        assert label_to_hour(hour_label(hour), as_end=True) == hour


def test_choice_lists_cover_the_day():
    assert START_CHOICES[0] == "12:00 AM" and START_CHOICES[-1] == "11:00 PM"
    assert END_CHOICES[0] == "1:00 AM" and END_CHOICES[-1] == "12:00 AM"
    assert len(START_CHOICES) == 24 and len(END_CHOICES) == 24
    assert WEEKDAYS == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------- Validation ----------

def test_valid_form_has_no_errors():
    errors = validate_form("Monday", "4:00 PM", "6:00 PM")
    assert errors == no_errors() and is_valid(errors)


def test_empty_form_reports_every_field():
    errors = validate_form("", "", "")
    assert errors["weekday"] and errors["start"] and errors["end"]
    assert not is_valid(errors)


def test_end_before_start_is_rejected():
    assert "later than the start" in validate_form("Monday", "6:00 PM", "4:00 PM")["end"]


def test_end_equal_to_start_is_rejected():
    assert validate_form("Monday", "4:00 PM", "4:00 PM")["end"]


def test_end_at_midnight_is_the_end_of_the_day():
    assert validate_form("Friday", "10:00 PM", "12:00 AM") == no_errors()
    assert to_time_slot("Friday", "10:00 PM", "12:00 AM").end_hour == 24


def test_unknown_day_or_time_is_rejected():
    assert validate_form("Funday", "4:00 PM", "6:00 PM")["weekday"]
    assert validate_form("Monday", "4:30 PM", "6:00 PM")["start"]


# ---------- Labels -> the model's TimeSlot ----------

def test_to_time_slot_uses_the_models_24_hour_integers():
    slot = to_time_slot("Monday", "4:00 PM", "6:00 PM")
    assert isinstance(slot, TimeSlot)
    assert slot.id is None
    assert slot.weekday is Weekday.MONDAY
    assert (slot.start_hour, slot.end_hour) == (16, 18)
    assert slot.duration_hours == 2


def test_round_trip_through_storage(tmp_path):
    storage.set_db_path(tmp_path / "slots.db")
    storage.init_db()
    new_id = storage.add_time_slot(to_time_slot("Wednesday", "5:00 PM", "7:00 PM"))
    rows = rows_from(storage.list_time_slots())
    assert rows == [{"id": str(new_id), "weekday": "Wednesday", "time": "5:00 PM – 7:00 PM", "hours": "2h"}]


# ---------- Rows for the page ----------

def test_rows_are_in_week_order_then_by_start():
    slots = [
        TimeSlot(id=1, weekday=Weekday.FRIDAY, start_hour=16, end_hour=18),
        TimeSlot(id=2, weekday=Weekday.MONDAY, start_hour=18, end_hour=20),
        TimeSlot(id=3, weekday=Weekday.MONDAY, start_hour=8, end_hour=9),
    ]
    assert [r["id"] for r in rows_from(slots)] == ["3", "2", "1"]
    assert total_hours(slots) == 5.0


def test_row_values_are_strings():
    row = row_from_slot(TimeSlot(id=7, weekday=Weekday.SUNDAY, start_hour=9, end_hour=12))
    assert all(isinstance(v, str) for v in row.values())
    assert row["time"] == "9:00 AM – 12:00 PM"
