"""
tests/test_assignment_storage.py
The Add Assignment form talking to the real backend.

The form's validated strings become a models.Assignment, go through
storage.add_assignment(ME), and come back through
storage.list_assignments(ME) as dashboard rows. These tests run that
round trip against a temporary database, which is the same proof the
mentor's "refresh the browser" check gives, without a browser.
"""

from datetime import date

import pytest

import storage

ME = storage.DEFAULT_USER_ID          # the built-in student; ownership tests live in test_ownership.py
from models import Assignment, Priority
from StudyFlow.assignments import RISK_NOT_RATED, rows_from, to_assignment

TODAY = date(2026, 9, 9)


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "form_test.db")
    storage.init_db()
    yield


# ---------- Form values -> Assignment ----------

def test_to_assignment_builds_a_real_model():
    a = to_assignment("Chemistry Lab", "Chemistry", "2026-09-15", "2.5", "HIGH")
    assert isinstance(a, Assignment)
    assert a.id is None                      # storage assigns the id
    assert a.name == "Chemistry Lab"
    assert a.subject == "Chemistry"
    assert a.due_date == date(2026, 9, 15)
    assert a.estimated_hours == 2.5
    assert a.priority is Priority.HIGH
    assert a.completed is False


def test_to_assignment_strips_whitespace_and_maps_every_priority():
    a = to_assignment("  Essay ", " English ", "2026-09-15", "1", "LOW")
    assert (a.name, a.subject) == ("Essay", "English")
    for name, member in [("LOW", Priority.LOW), ("MEDIUM", Priority.MEDIUM), ("HIGH", Priority.HIGH)]:
        assert to_assignment("A", "S", "2026-09-15", "1", name).priority is member


# ---------- Assignment -> storage -> rows ----------

def test_round_trip_through_storage():
    """Save through the real backend and read it back as a dashboard row."""
    new_id = storage.add_assignment(ME, to_assignment("Chemistry Lab", "Chemistry", "2026-09-15", "2.5", "HIGH"))
    rows = rows_from(storage.list_assignments(ME, include_completed=False), TODAY)
    assert rows == [{
        "id": str(new_id),
        "name": "Chemistry Lab",
        "subject": "Chemistry",
        "due": "Due in 6 days",
        "due_date": "2026-09-15",
        "due_pretty": "15 Sep 2026",
        "due_in_days": "6",
        "due_number": "6",
        "due_label": "days left",
        "hours": "2.5 hours",
        "priority": "HIGH",
        "risk": RISK_NOT_RATED,
    }]


def test_rows_come_back_in_due_date_order():
    """storage.list_assignments sorts by due date, so no re-sorting is needed."""
    storage.add_assignment(ME, to_assignment("Later", "S", "2026-09-20", "1", "LOW"))
    storage.add_assignment(ME, to_assignment("Sooner", "S", "2026-09-11", "1", "LOW"))
    storage.add_assignment(ME, to_assignment("Middle", "S", "2026-09-15", "1", "LOW"))
    names = [r["name"] for r in rows_from(storage.list_assignments(ME, include_completed=False), TODAY)]
    assert names == ["Sooner", "Middle", "Later"]


def test_completed_assignments_are_not_listed_on_the_dashboard():
    done_id = storage.add_assignment(ME, to_assignment("Done", "S", "2026-09-15", "1", "LOW"))
    storage.mark_assignment_complete(ME, done_id)
    storage.add_assignment(ME, to_assignment("Active", "S", "2026-09-15", "1", "LOW"))
    names = [r["name"] for r in rows_from(storage.list_assignments(ME, include_completed=False), TODAY)]
    assert names == ["Active"]


def test_decimal_hours_survive_the_database():
    storage.add_assignment(ME, to_assignment("Quarter", "S", "2026-09-15", "0.25", "LOW"))
    storage.add_assignment(ME, to_assignment("Half", "S", "2026-09-16", "1.5", "LOW"))
    hours = [r["hours"] for r in rows_from(storage.list_assignments(ME), TODAY)]
    assert hours == ["0.25 hours", "1.5 hours"]


def test_empty_database_gives_no_rows():
    assert rows_from(storage.list_assignments(ME, include_completed=False), TODAY) == []
