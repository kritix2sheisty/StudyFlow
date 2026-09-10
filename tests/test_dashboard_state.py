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


# ---------- Edit, complete, delete ----------

def add_one(state: DashboardState, name="Chemistry Lab", days=6, hours="2.5", priority="HIGH") -> str:
    """Add through the form and return the new row's id."""
    state.open_form()
    fill(state, name=name, due=(date.today() + timedelta(days=days)).isoformat(), hours=hours, priority=priority)
    state.submit_form()
    return next(r["id"] for r in state.assignments if r["name"] == name)


def test_open_edit_loads_the_stored_values_into_the_form():
    state = fresh_state()
    row_id = add_one(state)
    state.open_edit(row_id)
    assert state.form_open is True and state.is_editing is True
    assert state.editing_id == row_id
    assert (state.form_name, state.form_subject) == ("Chemistry Lab", "Chemistry")
    assert state.form_due == (date.today() + timedelta(days=6)).isoformat()
    assert state.form_hours == "2.5" and state.form_priority == "HIGH"


def test_edit_updates_the_database_row_not_a_copy():
    state = fresh_state()
    row_id = add_one(state)
    state.open_edit(row_id)
    state.set_form_hours("4")
    state.set_form_priority("LOW")
    state.set_form_due((date.today() + timedelta(days=2)).isoformat())
    state.submit_form()

    stored = storage.list_assignments()
    assert len(stored) == 1                      # updated in place, not duplicated
    assert stored[0].id == int(row_id)
    assert stored[0].estimated_hours == 4 and stored[0].priority.name == "LOW"
    assert stored[0].due_date == date.today() + timedelta(days=2)
    assert state.form_open is False and state.is_editing is False
    assert state.assignments[0]["hours"] == "4 hours"


def test_edit_validation_keeps_edit_mode():
    state = fresh_state()
    row_id = add_one(state)
    state.open_edit(row_id)
    state.set_form_name("")
    state.submit_form()
    assert state.form_open is True and state.editing_id == row_id
    assert state.form_errors["name"]
    assert storage.list_assignments()[0].name == "Chemistry Lab"


def test_open_edit_on_a_missing_assignment_does_not_open_the_form():
    state = fresh_state()
    state.open_edit("999")
    assert state.form_open is False


def test_complete_removes_it_from_the_active_list_but_keeps_the_row():
    state = fresh_state()
    row_id = add_one(state)
    add_one(state, name="Other", days=3)
    state.complete_assignment(row_id)
    assert [r["name"] for r in state.assignments] == ["Other"]
    assert state.assignment_count == "1"
    done = [a for a in storage.list_assignments() if a.id == int(row_id)]
    assert done and done[0].completed is True


def test_delete_asks_then_removes_the_row():
    state = fresh_state()
    row_id = add_one(state)
    state.ask_delete(row_id, "Chemistry Lab")
    assert state.delete_open is True and state.delete_name == "Chemistry Lab"
    assert len(storage.list_assignments()) == 1          # nothing gone yet
    state.confirm_delete()
    assert state.delete_open is False and state.delete_id == ""
    assert storage.list_assignments() == []
    assert state.assignments == []


def test_confirming_a_delete_for_a_row_that_is_already_gone_does_not_crash():
    """A stale confirmation (the row was removed elsewhere) must not error or lie."""
    state = fresh_state()
    row_id = add_one(state)
    state.ask_delete(row_id, "Chemistry Lab")
    storage.delete_assignment(int(row_id))            # gone behind the dialog's back
    state.confirm_delete()
    assert state.delete_open is False
    assert state.assignments == []
    assert storage.list_assignments() == []


def test_cancelling_delete_keeps_the_row():
    state = fresh_state()
    row_id = add_one(state)
    state.ask_delete(row_id, "Chemistry Lab")
    state.cancel_delete()
    assert state.delete_open is False
    assert len(storage.list_assignments()) == 1
    state.ask_delete(row_id, "Chemistry Lab")
    state.set_delete_open(False)                         # Escape / click outside
    assert state.delete_open is False
    assert len(storage.list_assignments()) == 1


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
