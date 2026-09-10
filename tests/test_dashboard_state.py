"""
tests/test_dashboard_state.py
The Reflex State's event handlers, driven directly against a
temporary database.

This is the browser flow without the browser: open the form, type
values, submit, and check what storage.py now holds and what the
dashboard would show. It pins the wiring Form -> validate ->
Assignment -> add_assignment() -> list_assignments() -> State.
"""

from datetime import date, timedelta

import pytest

import storage
from StudyFlow.assignments import RISK_NOT_RATED
from StudyFlow.StudyFlow import DashboardState


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "state_test.db")
    storage.init_db()
    yield


def fresh_state() -> DashboardState:
    return DashboardState(_reflex_internal_init=True)


def fill(state: DashboardState, name="Chemistry Lab", subject="Chemistry",
         due=None, hours="2.5", priority="HIGH") -> None:
    state.set_form_name(name)
    state.set_form_subject(subject)
    state.set_form_due(due or (date.today() + timedelta(days=6)).isoformat())
    state.set_form_hours(hours)
    state.set_form_priority(priority)


def test_load_assignments_reads_the_database():
    state = fresh_state()
    assert state.assignments == []
    storage.add_assignment(storage.Assignment(name="Stored", subject="S",
                                              due_date=date.today() + timedelta(days=2),
                                              estimated_hours=1))
    state.load_assignments()
    assert [r["name"] for r in state.assignments] == ["Stored"]
    assert state.assignment_count == "1"


def test_submit_saves_through_storage_and_refreshes_the_dashboard():
    state = fresh_state()
    state.open_form()
    fill(state)
    state.submit_form()

    stored = storage.list_assignments()
    assert len(stored) == 1
    assert stored[0].name == "Chemistry Lab"
    assert stored[0].estimated_hours == 2.5
    assert stored[0].priority.name == "HIGH"

    assert state.form_open is False
    assert state.form_name == "" and state.form_hours == ""
    assert state.assignments[0]["name"] == "Chemistry Lab"
    assert state.assignments[0]["risk"] == RISK_NOT_RATED
    assert state.assignment_count == "1"
    assert state.required_hours == "2.5"


def test_submit_with_an_empty_form_saves_nothing_and_keeps_the_form_open():
    state = fresh_state()
    state.open_form()
    state.submit_form()
    assert storage.list_assignments() == []
    assert state.form_open is True
    assert all(state.form_errors[f] for f in ("name", "subject", "due", "hours"))
    assert state.form_errors["priority"] == ""      # MEDIUM by default


def test_decimal_hours_and_due_date_order():
    state = fresh_state()
    state.open_form()
    fill(state, name="Later", due=(date.today() + timedelta(days=9)).isoformat(), hours="1.5")
    state.submit_form()
    state.open_form()
    fill(state, name="Sooner", due=(date.today() + timedelta(days=2)).isoformat(), hours="0.25")
    state.submit_form()
    assert [r["name"] for r in state.assignments] == ["Sooner", "Later"]
    assert [r["hours"] for r in state.assignments] == ["0.25 hours", "1.5 hours"]
    assert state.assignment_count == "2"


def test_cancel_clears_the_form_without_saving():
    state = fresh_state()
    state.open_form()
    fill(state, name="Never saved")
    state.close_form()
    assert state.form_open is False
    assert state.form_name == ""
    assert storage.list_assignments() == []


def test_save_failure_shows_a_message_and_keeps_the_form_open(monkeypatch):
    import StudyFlow.StudyFlow as page

    def boom(_assignment):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(page, "add_assignment", boom)
    state = fresh_state()
    state.open_form()
    fill(state)
    state.submit_form()
    assert state.form_open is True
    assert "could not save" in state.form_save_error
    assert state.form_name == "Chemistry Lab"          # nothing was thrown away
    assert storage.list_assignments() == []
