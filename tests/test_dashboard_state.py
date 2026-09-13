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

ME = storage.DEFAULT_USER_ID          # the built-in student; ownership tests live in test_ownership.py
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
    storage.add_assignment(ME, storage.Assignment(name="Stored", subject="S",
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

    stored = storage.list_assignments(ME)
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
    assert storage.list_assignments(ME) == []
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
    assert storage.list_assignments(ME) == []


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

    stored = storage.list_assignments(ME)
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
    assert storage.list_assignments(ME)[0].name == "Chemistry Lab"


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
    done = [a for a in storage.list_assignments(ME) if a.id == int(row_id)]
    assert done and done[0].completed is True


def test_delete_asks_then_removes_the_row():
    state = fresh_state()
    row_id = add_one(state)
    state.ask_delete(row_id, "Chemistry Lab")
    assert state.delete_open is True and state.delete_name == "Chemistry Lab"
    assert len(storage.list_assignments(ME)) == 1          # nothing gone yet
    state.confirm_delete()
    assert state.delete_open is False and state.delete_id == ""
    assert storage.list_assignments(ME) == []
    assert state.assignments == []


def test_confirming_a_delete_for_a_row_that_is_already_gone_does_not_crash():
    """A stale confirmation (the row was removed elsewhere) must not error or lie."""
    state = fresh_state()
    row_id = add_one(state)
    state.ask_delete(row_id, "Chemistry Lab")
    storage.delete_assignment(ME, int(row_id))            # gone behind the dialog's back
    state.confirm_delete()
    assert state.delete_open is False
    assert state.assignments == []
    assert storage.list_assignments(ME) == []


def test_cancelling_delete_keeps_the_row():
    state = fresh_state()
    row_id = add_one(state)
    state.ask_delete(row_id, "Chemistry Lab")
    state.cancel_delete()
    assert state.delete_open is False
    assert len(storage.list_assignments(ME)) == 1
    state.ask_delete(row_id, "Chemistry Lab")
    state.set_delete_open(False)                         # Escape / click outside
    assert state.delete_open is False
    assert len(storage.list_assignments(ME)) == 1


# ---------- Study time ----------

def add_slot(state: DashboardState, weekday="Monday", start="4:00 PM", end="6:00 PM") -> None:
    state.open_slot_form()
    state.set_slot_weekday(weekday)
    state.set_slot_start(start)
    state.set_slot_end(end)
    state.submit_slot_form()


def test_load_data_reads_slots_and_assignments():
    state = fresh_state()
    storage.add_time_slot(ME, storage.TimeSlot(weekday=storage.Weekday.WEDNESDAY, start_hour=17, end_hour=19))
    state.load_data()
    assert [r["time"] for r in state.slots] == ["5:00 PM – 7:00 PM"]
    assert state.slot_hours == "2"
    assert state.assignments == []


def test_add_study_time_saves_the_models_24_hour_integers():
    state = fresh_state()
    add_slot(state, "Monday", "4:00 PM", "6:00 PM")
    stored = storage.list_time_slots(ME)
    assert len(stored) == 1
    assert stored[0].weekday is storage.Weekday.MONDAY
    assert (stored[0].start_hour, stored[0].end_hour) == (16, 18)
    assert state.slot_form_open is False
    assert state.slots[0]["weekday"] == "Monday" and state.slots[0]["time"] == "4:00 PM – 6:00 PM"
    assert state.slot_hours == "2"


def test_two_slots_show_in_week_order_with_the_total():
    state = fresh_state()
    add_slot(state, "Wednesday", "5:00 PM", "7:00 PM")
    add_slot(state, "Monday", "4:00 PM", "6:00 PM")
    assert [r["weekday"] for r in state.slots] == ["Monday", "Wednesday"]
    assert state.slot_hours == "4"


def test_end_before_start_is_rejected_and_nothing_is_saved():
    state = fresh_state()
    add_slot(state, "Monday", "6:00 PM", "4:00 PM")
    assert state.slot_form_open is True
    assert "later than the start" in state.slot_errors["end"]
    assert storage.list_time_slots(ME) == []


def test_empty_slot_form_is_rejected():
    state = fresh_state()
    add_slot(state, "", "", "")
    assert state.slot_form_open is True
    assert all(state.slot_errors[f] for f in ("weekday", "start", "end"))
    assert storage.list_time_slots(ME) == []


def test_cancel_slot_form_resets_to_the_defaults():
    state = fresh_state()
    state.open_slot_form()
    state.set_slot_weekday("Friday")
    state.close_slot_form()
    assert state.slot_form_open is False
    assert (state.slot_weekday, state.slot_start, state.slot_end) == ("Monday", "4:00 PM", "6:00 PM")
    assert storage.list_time_slots(ME) == []


def test_delete_slot_asks_then_removes():
    state = fresh_state()
    add_slot(state)
    slot_id = state.slots[0]["id"]
    state.ask_delete_slot(slot_id, "Monday 4:00 PM – 6:00 PM")
    assert state.slot_delete_open is True and len(storage.list_time_slots(ME)) == 1
    state.confirm_delete_slot()
    assert state.slot_delete_open is False
    assert storage.list_time_slots(ME) == [] and state.slots == []
    assert state.slot_hours == "0"


def test_cancel_delete_slot_keeps_it():
    state = fresh_state()
    add_slot(state)
    state.ask_delete_slot(state.slots[0]["id"], "Monday 4:00 PM – 6:00 PM")
    state.set_slot_delete_open(False)
    assert state.slot_delete_open is False and len(storage.list_time_slots(ME)) == 1


# ---------- Generate Study Plan ----------

def slot_on(days_from_today: int, start: int, end: int) -> None:
    """Study time on the weekday that falls `days_from_today` from today."""
    weekday = storage.Weekday((date.today() + timedelta(days=days_from_today)).weekday())
    storage.add_time_slot(ME, storage.TimeSlot(weekday=weekday, start_hour=start, end_hour=end))


def test_generate_with_no_assignments_explains_and_makes_no_plan():
    state = fresh_state()
    slot_on(0, 16, 18)
    state.generate_study_plan()
    assert state.has_plan is False
    assert "assignments" in state.plan_message


def test_generate_with_no_study_time_explains_and_makes_no_plan():
    state = fresh_state()
    add_one(state)
    state.generate_study_plan()
    assert state.has_plan is False
    assert "study times" in state.plan_message


def test_generate_places_the_work_into_the_saved_study_periods():
    """
    The mentor's controlled example, relative to today: study time
    today, tomorrow and the day after (4-6 PM); Math 2h due in 3
    days; Physics 5h due in 4 days. Math takes today, Physics the
    next two days, 1h of Physics left over.
    """
    state = fresh_state()
    slot_on(0, 16, 18)
    slot_on(1, 16, 18)
    slot_on(2, 16, 18)
    add_one(state, name="Math", days=3, hours="2", priority="MEDIUM")
    add_one(state, name="Physics", days=4, hours="5", priority="HIGH")
    state.generate_study_plan()

    assert state.has_plan is True and state.plan_message == ""
    assert [(b.label, b.time) for b in state.plan_days[0].blocks] == [("Math", "4 PM–6 PM")]
    assert [b.label for b in state.plan_days[1].blocks] == ["Physics"]
    assert [b.label for b in state.plan_days[2].blocks] == ["Physics"]
    assert state.today_plan == [{"time": "4 PM–6 PM", "label": "Math", "is_break": "no"}]
    assert (state.plan_required, state.plan_scheduled, state.plan_unscheduled, state.plan_completion) == ("7.0", "6.0", "1.0", "86")
    assert state.progress_value == 86

    by_name = {r.name: r for r in state.plan_statuses}
    assert by_name["Math"].status == "COMPLETE" and by_name["Math"].percent == 100
    assert by_name["Physics"].status == "PARTIAL" and by_name["Physics"].remaining == "1.0"
    assert by_name["Physics"].percent == 80
    assert by_name["Physics"].subject == "Chemistry"          # fill()'s default subject
    # The assignment cards now carry the real risk instead of NOT RATED.
    # Physics has 1h left and every hour before its deadline is taken.
    assert {r["name"]: r["risk"] for r in state.assignments} == {"Math": "LOW", "Physics": "CRITICAL"}


def test_completed_assignments_are_counted_but_never_planned():
    state = fresh_state()
    slot_on(0, 16, 18)
    row_id = add_one(state, name="Done", days=2)
    state.complete_assignment(row_id)
    add_one(state, name="Live", days=3, hours="1")
    assert state.completed_names == ["Done"] and state.completed_count == "1"
    assert state.assignment_count == "1"
    state.generate_study_plan()
    assert [r.name for r in state.plan_statuses] == ["Live"]
    assert state.plan_required == "1.0" and state.plan_completion == "100"


def test_generate_marks_work_that_cannot_fit_as_at_risk():
    """Due today, 6h, only 2h of study time today: partial, critical, 33%."""
    state = fresh_state()
    slot_on(0, 16, 18)
    slot_on(1, 16, 18)
    add_one(state, name="Rush", days=0, hours="6", priority="HIGH")
    state.generate_study_plan()
    assert state.has_plan is True
    row = state.plan_statuses[0]
    assert row.status == "PARTIAL" and row.remaining == "4.0" and row.risk == "CRITICAL"
    assert state.plan_completion == "33"
    assert state.assignments[0]["risk"] == "CRITICAL"


def test_generate_failure_keeps_the_dashboard_usable(monkeypatch):
    import StudyFlow.StudyFlow as page

    def boom(*args, **kwargs):
        raise RuntimeError("engine on fire")

    monkeypatch.setattr(page, "generate_study_plan", boom)
    state = fresh_state()
    slot_on(0, 16, 18)
    add_one(state)
    state.generate_study_plan()
    assert state.has_plan is False
    assert "could not build a plan" in state.plan_message
    assert state.assignments                       # still loaded and usable


# ---------- Plan invalidation ----------

def planned_state() -> DashboardState:
    """A state with study time, two assignments and a generated plan."""
    state = fresh_state()
    slot_on(0, 16, 18)
    slot_on(1, 16, 18)
    state.load_data()                                 # pick up the seeded slots, as a page load would
    add_one(state, name="Math", days=3, hours="2", priority="MEDIUM")
    add_one(state, name="Physics", days=4, hours="1", priority="HIGH")
    state.generate_study_plan()
    assert state.has_plan is True and state.plan_stale is False
    assert all(r["risk"] == "LOW" for r in state.assignments)   # the plan stamped real risk
    return state


def assert_plan_cleared(state: DashboardState, what: str) -> None:
    """Nothing generated is left to display, and the reason is stated."""
    assert state.has_plan is False and state.plan_stale is True
    assert what in state.plan_message and "needs to be regenerated" in state.plan_message
    assert state.plan_days == [] and state.today_plan == [] and state.plan_statuses == []
    assert (state.plan_required, state.plan_scheduled, state.plan_unscheduled, state.plan_completion) == ("0.0", "0.0", "0.0", "0")
    assert state.progress_value == 0
    assert all(r["risk"] == "NOT RATED" for r in state.assignments)


def test_editing_an_assignment_invalidates_the_plan():
    state = planned_state()
    state.open_edit(state.assignments[0]["id"])
    state.set_form_hours("5")
    state.submit_form()
    assert_plan_cleared(state, "assignments")


def test_adding_an_assignment_invalidates_the_plan():
    state = planned_state()
    add_one(state, name="Essay", days=5, hours="1", priority="LOW")
    assert_plan_cleared(state, "assignments")


def test_completing_an_assignment_invalidates_the_plan():
    state = planned_state()
    state.complete_assignment(state.assignments[0]["id"])
    assert_plan_cleared(state, "assignments")


def test_deleting_an_assignment_invalidates_the_plan():
    state = planned_state()
    state.ask_delete(state.assignments[0]["id"], "Math")
    state.confirm_delete()
    assert_plan_cleared(state, "assignments")


def test_adding_study_time_invalidates_the_plan():
    state = planned_state()
    add_slot(state, "Sunday", "9:00 AM", "11:00 AM")
    assert_plan_cleared(state, "study times")


def test_deleting_study_time_invalidates_the_plan():
    state = planned_state()
    state.ask_delete_slot(state.slots[0]["id"], "some slot")
    state.confirm_delete_slot()
    assert_plan_cleared(state, "study times")


def test_regenerating_clears_the_stale_flag_and_uses_the_new_inputs():
    state = planned_state()
    state.complete_assignment(state.assignments[0]["id"])       # Math (2h) done; Physics (1h) left
    state.generate_study_plan()
    assert state.has_plan is True and state.plan_stale is False and state.plan_message == ""
    assert state.plan_required == "1.0" and state.plan_scheduled == "1.0"


def test_changes_before_any_plan_do_not_claim_a_plan_went_stale():
    state = fresh_state()
    slot_on(0, 16, 18)
    add_one(state)
    assert state.has_plan is False and state.plan_stale is False and state.plan_message == ""


def test_invalidation_keeps_assignments_and_study_slots_and_generate_works_again():
    """Only the generated values go; the student's data stays, and a new plan can be built from it."""
    state = planned_state()
    names_before = [r["name"] for r in state.assignments]
    slots_before = len(state.slots)

    add_slot(state, "Sunday", "9:00 AM", "11:00 AM")            # invalidates via study time
    assert_plan_cleared(state, "study times")
    assert [r["name"] for r in state.assignments] == names_before
    assert len(state.slots) == slots_before + 1

    state.ask_delete(state.assignments[1]["id"], "Physics")     # invalidates via assignments
    state.confirm_delete()
    assert_plan_cleared(state, "assignments")
    assert "assignments and study times" in state.plan_message   # both kinds changed since the plan
    assert [r["name"] for r in state.assignments] == ["Math"]
    assert len(state.slots) == slots_before + 1

    state.generate_study_plan()
    assert state.has_plan is True and state.plan_stale is False and state.plan_message == ""
    assert state.plan_required == "2.0" and state.plan_scheduled == "2.0" and state.plan_completion == "100"
    assert state.plan_days and state.plan_statuses
    assert all(r["risk"] != "NOT RATED" for r in state.assignments)


def test_completing_an_assignment_that_is_already_gone_does_not_invalidate_the_plan():
    """Nothing changed in the database, so the plan is not declared stale."""
    state = planned_state()
    missing = state.assignments[0]["id"]
    storage.delete_assignment(ME, int(missing))                     # gone behind the app's back
    state.complete_assignment(missing)
    assert state.has_plan is True and state.plan_stale is False
    assert all(r["id"] != missing for r in state.assignments)   # the list was still refreshed


def test_editing_an_assignment_that_is_already_gone_shows_an_error_and_keeps_the_plan():
    state = planned_state()
    missing = state.assignments[0]["id"]
    state.open_edit(missing)
    storage.delete_assignment(ME, int(missing))
    state.set_form_hours("5")
    state.submit_form()
    assert "no longer exists" in state.form_save_error
    assert state.form_open is True
    assert state.has_plan is True and state.plan_stale is False


def test_a_failed_change_leaves_the_plan_alone():
    """Validation failure changes nothing, so the plan stays."""
    state = planned_state()
    state.open_edit(state.assignments[0]["id"])
    state.set_form_hours("not a number")
    state.submit_form()
    assert state.has_plan is True and state.plan_stale is False


def test_cancelled_delete_leaves_the_plan_alone():
    state = planned_state()
    state.ask_delete(state.assignments[0]["id"], "Math")
    state.cancel_delete()
    assert state.has_plan is True and state.plan_stale is False


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
    assert storage.list_assignments(ME) == []


# ---------- Overdue dates (v1.1) ----------

def past(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def test_adding_with_a_past_date_saves_and_says_so():
    state = fresh_state()
    state.open_form()
    assert state.form_notice == ""
    fill(state, name="History Essay", due=past(3), hours="1", priority="HIGH")
    assert "already passed" in state.form_notice                 # shown while the form is open
    assert all(v == "" for v in state.form_errors.values())      # not an error
    toast = state.submit_form()
    assert "History Essay" in str(toast.args) and "overdue" in str(toast.args)
    assert any(r["name"] == "History Essay" for r in state.assignments)
    assert state.form_open is False and state.form_notice == ""  # cleared with the form


def test_notice_follows_the_chosen_date():
    state = fresh_state()
    state.open_form()
    state.set_form_due(past(1))
    assert state.form_notice != ""
    state.set_form_due(date.today().isoformat())
    assert state.form_notice == ""
    state.set_form_due((date.today() + timedelta(days=2)).isoformat())
    assert state.form_notice == ""
    state.set_form_due("nonsense")
    assert state.form_notice == ""
    state.close_form()
    assert state.form_notice == ""


def test_future_dates_keep_the_plain_success_message():
    state = fresh_state()
    state.open_form()
    fill(state, name="Normal", due=(date.today() + timedelta(days=4)).isoformat())
    toast = state.submit_form()
    assert "Added Normal" in str(toast.args) and "overdue" not in str(toast.args)


def test_editing_to_a_past_date_saves_with_the_notice():
    state = fresh_state()
    row_id = add_one(state, name="Essay", days=3)
    state.open_edit(row_id)
    assert state.form_notice == ""
    state.set_form_due(past(2))
    assert "already passed" in state.form_notice
    toast = state.submit_form()
    assert "Saved changes to Essay" in str(toast.args) and "overdue" in str(toast.args)
    assert next(r for r in state.assignments if r["id"] == row_id)["due"] == "Overdue by 2 days"


def test_editing_other_fields_of_an_overdue_assignment_is_not_blocked():
    state = fresh_state()
    state.open_form()
    fill(state, name="Late lab", due=past(5), hours="1")
    state.submit_form()
    row_id = next(r["id"] for r in state.assignments if r["name"] == "Late lab")
    state.open_edit(row_id)
    assert "already passed" in state.form_notice                 # the loaded date is in the past
    state.set_form_hours("2.5")
    toast = state.submit_form()
    assert "Saved changes to Late lab" in str(toast.args)
    assert next(r for r in state.assignments if r["id"] == row_id)["hours"] == "2.5 hours"


def test_overdue_card_does_not_read_zero_days_left():
    state = fresh_state()
    state.open_form()
    fill(state, name="Late lab", due=past(3), hours="1")
    state.submit_form()
    state.open_form()
    fill(state, name="Today quiz", due=date.today().isoformat(), hours="1")
    state.submit_form()
    by_name = {r["name"]: r for r in state.assignments}
    late, today_row = by_name["Late lab"], by_name["Today quiz"]
    assert (late["due_number"], late["due_label"]) == ("3", "days overdue")
    assert late["due"] == "Overdue by 3 days"
    assert (today_row["due_number"], today_row["due_label"]) == ("Today", "due")
    for r in (late, today_row):
        assert (r["due_number"], r["due_label"]) != ("0", "days left")


def test_engine_treatment_of_overdue_work_is_unchanged():
    """Overdue work that fits is COMPLETE / LOW; overdue work that cannot fit is CRITICAL."""
    state = fresh_state()
    slot_on(0, 16, 18)
    state.load_data()
    state.open_form()
    fill(state, name="Late essay", due=past(3), hours="1", priority="HIGH")
    state.submit_form()
    state.generate_study_plan()
    row = next(r for r in state.plan_statuses if r.name == "Late essay")
    assert (row.status, row.risk) == ("COMPLETE", "LOW")
    assert state.today_plan and state.today_plan[0]["label"] == "Late essay"   # placed as soon as possible

    state.open_form()
    fill(state, name="Late thesis", due=past(10), hours="6", priority="HIGH")
    state.submit_form()
    state.generate_study_plan()
    by_name = {r.name: r for r in state.plan_statuses}
    assert by_name["Late essay"].status == "COMPLETE"
    assert by_name["Late thesis"].status == "PARTIAL" and by_name["Late thesis"].risk == "CRITICAL"


# ---------- Plan freshness: the fingerprint safety net (v1.2) ----------

from StudyFlow import plan_view as _plan_view


def current_fingerprint() -> str:
    return _plan_view.plan_input_fingerprint(
        storage.list_assignments(ME, include_completed=False), storage.list_time_slots(ME))


def stored(name: str):
    return next(a for a in storage.list_assignments(ME) if a.name == name)


def assert_plan_stale_after_load(state: DashboardState) -> None:
    state.load_data()
    assert_plan_cleared(state, "assignments or study times")
    assert state.plan_fingerprint == ""


def test_generating_stores_the_fingerprint_of_the_inputs_used():
    state = planned_state()
    assert state.plan_fingerprint == current_fingerprint() != ""


def test_reloading_with_identical_data_keeps_the_plan_and_its_risks():
    state = planned_state()
    days_before, statuses_before, fp = state.plan_days, state.plan_statuses, state.plan_fingerprint
    state.load_data()
    assert state.has_plan is True and state.plan_stale is False and state.plan_message == ""
    assert state.plan_days == days_before and state.plan_statuses == statuses_before
    assert state.plan_fingerprint == fp
    assert all(r["risk"] == "LOW" for r in state.assignments)        # re-stamped from the plan, not NOT RATED


def test_changing_hours_in_the_database_makes_the_plan_stale():
    state = planned_state()
    a = stored("Math"); a.estimated_hours = 5; storage.update_assignment(ME, a)
    assert_plan_stale_after_load(state)


def test_changing_a_due_date_in_the_database_makes_the_plan_stale():
    state = planned_state()
    a = stored("Math"); a.due_date = a.due_date + timedelta(days=2); storage.update_assignment(ME, a)
    assert_plan_stale_after_load(state)


def test_adding_an_assignment_in_the_database_makes_the_plan_stale():
    state = planned_state()
    storage.add_assignment(ME, storage.Assignment(name="Essay", subject="E", due_date=date.today() + timedelta(days=5),
                                              estimated_hours=1, priority=storage.Priority.LOW))
    assert_plan_stale_after_load(state)
    assert any(r["name"] == "Essay" for r in state.assignments)      # the data itself is loaded


def test_deleting_an_assignment_in_the_database_makes_the_plan_stale():
    state = planned_state()
    storage.delete_assignment(ME, stored("Physics").id)
    assert_plan_stale_after_load(state)
    assert all(r["name"] != "Physics" for r in state.assignments)


def test_completing_an_assignment_in_the_database_makes_the_plan_stale():
    state = planned_state()
    storage.mark_assignment_complete(ME, stored("Math").id, True)
    assert_plan_stale_after_load(state)


def test_changing_a_slot_in_the_database_makes_the_plan_stale():
    state = planned_state()
    slot = storage.list_time_slots(ME)[0]; slot.end_hour = 19; storage.update_time_slot(ME, slot)
    assert_plan_stale_after_load(state)


def test_deleting_a_slot_in_the_database_makes_the_plan_stale():
    state = planned_state()
    storage.delete_time_slot(ME, storage.list_time_slots(ME)[0].id)
    assert_plan_stale_after_load(state)
    assert len(state.slots) == 1


def test_stale_plan_leaves_nothing_for_the_pages_to_render():
    state = planned_state()
    storage.delete_assignment(ME, stored("Physics").id)
    state.load_data()
    assert state.has_plan is False
    assert state.plan_days == [] and state.today_plan == [] and state.plan_statuses == []
    assert (state.plan_scheduled, state.plan_completion) == ("0.0", "0")
    assert all(r["risk"] == "NOT RATED" for r in state.assignments)
    assert "needs to be regenerated" in state.plan_message


def test_explicit_invalidation_and_the_safety_net_agree():
    """A change through the app invalidates first; a later load finds nothing to do."""
    state = planned_state()
    state.complete_assignment(state.assignments[0]["id"])
    assert_plan_cleared(state, "assignments")
    message = state.plan_message
    state.load_data()
    assert state.has_plan is False and state.plan_message == message  # not re-stamped with a second reason


def test_regenerating_after_a_database_change_refreshes_the_fingerprint():
    state = planned_state()
    old = state.plan_fingerprint
    storage.delete_assignment(ME, stored("Physics").id)
    state.load_data()
    state.generate_study_plan()
    assert state.has_plan is True and state.plan_fingerprint == current_fingerprint() != old


def test_no_data_behaviour_is_unchanged_by_the_safety_net():
    state = fresh_state()
    state.load_data()                                  # nothing stored, no plan: nothing to compare
    assert state.has_plan is False and state.plan_stale is False and state.plan_message == ""
    state.generate_study_plan()
    assert state.has_plan is False and "assignments" in state.plan_message
    assert state.plan_fingerprint == ""
