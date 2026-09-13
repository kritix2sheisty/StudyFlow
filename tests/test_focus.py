"""
tests/test_focus.py
The Focus page: which of today's blocks is the current session, the
countdown, and the FocusState transitions (ready -> running -> paused
-> complete -> break -> break over), with the clock under test control.
"""

from datetime import date, timedelta

import pytest

import storage
from models import Assignment, Priority, TimeSlot, Weekday
from schedule_builder import DEFAULT_BREAK_MINUTES
from study_plan import generate_study_plan
from StudyFlow import focus
from StudyFlow.StudyFlow import DashboardState, FocusState

MONDAY = date(2026, 8, 17)
SLOTS = [TimeSlot(id=1, weekday=Weekday.MONDAY, start_hour=16, end_hour=18),
         TimeSlot(id=2, weekday=Weekday.MONDAY, start_hour=19, end_hour=20)]
MATH = Assignment(id=1, name="Math", subject="Mathematics", due_date=MONDAY + timedelta(days=3), estimated_hours=2, priority=Priority.HIGH)
CS = Assignment(id=2, name="CS", subject="Computer Science", due_date=MONDAY + timedelta(days=4), estimated_hours=1)


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "focus_test.db")
    storage.init_db()
    yield


@pytest.fixture
def sessions():
    plan = generate_study_plan([MATH, CS], SLOTS, today=MONDAY)
    return focus.sessions_for_today(plan, [MATH, CS], MONDAY)


# ---------- The pure helpers ----------

def test_todays_sessions_are_the_work_blocks_with_their_subjects(sessions):
    assert [(s.label, s.subject, s.time, s.start_minute, s.end_minute, s.minutes) for s in sessions] == [
        ("Math", "Mathematics", "4 PM–6 PM", 16 * 60, 18 * 60, 120),
        ("CS", "Computer Science", "7 PM–8 PM", 19 * 60, 20 * 60, 60),
    ]


def test_breaks_are_not_sessions():
    slots = [TimeSlot(id=1, weekday=Weekday.MONDAY, start_hour=16, end_hour=18)]
    a = Assignment(id=1, name="A", subject="A", due_date=MONDAY + timedelta(days=1), estimated_hours=1, priority=Priority.HIGH)
    b = Assignment(id=2, name="B", subject="B", due_date=MONDAY + timedelta(days=1), estimated_hours=0.5)
    plan = generate_study_plan([a, b], slots, today=MONDAY)
    labels = [s.label for s in focus.sessions_for_today(plan, [a, b], MONDAY)]
    assert labels == ["A", "B"]


def test_pick_finds_the_block_that_contains_now(sessions):
    current, nxt = focus.pick(sessions, 16 * 60 + 30)
    assert current.label == "Math" and nxt.label == "CS"


def test_pick_before_the_first_block_has_no_current_but_a_next(sessions):
    current, nxt = focus.pick(sessions, 15 * 60)
    assert current is None and nxt.label == "Math"


def test_pick_between_blocks(sessions):
    current, nxt = focus.pick(sessions, 18 * 60 + 30)
    assert current is None and nxt.label == "CS"


def test_pick_after_the_last_block_has_nothing(sessions):
    assert focus.pick(sessions, 20 * 60 + 1) == (None, None)


def test_pick_at_block_edges(sessions):
    assert focus.pick(sessions, 16 * 60)[0].label == "Math"          # start is inside
    assert focus.pick(sessions, 18 * 60)[0] is None                  # end is not


def test_pick_after_a_finished_session_moves_on(sessions):
    current, nxt = focus.pick(sessions, 16 * 60 + 30, after="Math")
    assert current is None and nxt.label == "CS"
    assert focus.pick(sessions, 19 * 60 + 10, after="CS") == (None, None)


def test_clock_formats_minutes_and_seconds():
    assert focus.clock(2700) == "45:00"
    assert focus.clock(61) == "01:01"
    assert focus.clock(3600) == "60:00"
    assert focus.clock(0) == "00:00"
    assert focus.clock(-5) == "00:00"


# ---------- Today's sessions live on the dashboard state ----------

def slot_on(days_from_today: int, start: int, end: int) -> None:
    weekday = storage.Weekday((date.today() + timedelta(days=days_from_today)).weekday())
    storage.add_time_slot(storage.TimeSlot(weekday=weekday, start_hour=start, end_hour=end))


def test_generating_a_plan_records_todays_sessions_and_invalidation_clears_them():
    slot_on(0, 16, 18)
    storage.add_assignment(Assignment(name="Math", subject="Mathematics", due_date=date.today() + timedelta(days=2),
                                      estimated_hours=2, priority=Priority.HIGH))
    state = DashboardState(_reflex_internal_init=True)
    state.load_data()
    state.generate_study_plan()
    assert [(s.label, s.subject, s.minutes) for s in state.today_sessions] == [("Math", "Mathematics", 120)]
    state._invalidate_plan("assignments")
    assert state.today_sessions == []


# ---------- FocusState transitions ----------

class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr("StudyFlow.StudyFlow.time.time", fake)
    return fake


def ready_state(sessions, now_minute=16 * 60 + 30) -> FocusState:
    state = FocusState(_reflex_internal_init=True)
    state._apply(sessions, has_plan=True, now_minute=now_minute)
    return state


def test_no_plan_means_no_session(sessions):
    state = FocusState(_reflex_internal_init=True)
    state._apply(sessions, has_plan=False, now_minute=16 * 60 + 30)
    assert state.mode == "none" and state.has_plan is False and state.label == ""


def test_a_plan_with_nothing_now_shows_the_next_session(sessions):
    state = ready_state(sessions, now_minute=15 * 60)
    assert state.mode == "none" and state.has_plan is True
    assert state.label == "" and state.next_label == "Math" and state.next_time == "4 PM–6 PM"


def test_a_current_block_is_ready_with_its_full_length(sessions):
    state = ready_state(sessions)
    assert state.mode == "ready"
    assert (state.label, state.subject, state.time_label, state.session_minutes) == ("Math", "Mathematics", "4 PM–6 PM", 120)
    assert state.total_seconds == state.remaining_seconds == 120 * 60
    assert state.clock == "120:00"
    assert (state.next_label, state.next_time) == ("CS", "7 PM–8 PM")


def test_start_pause_resume_reset(sessions, clock):
    state = ready_state(sessions)
    state.start_session()
    assert state.mode == "running"
    clock.t += 90                       # a minute and a half passes
    state.tick()
    assert state.remaining_seconds == 120 * 60 - 90 and state.clock == "118:30"

    state.pause_session()
    assert state.mode == "paused"
    clock.t += 600                      # paused time does not count
    state.tick()
    assert state.remaining_seconds == 120 * 60 - 90

    state.start_session()               # resume
    clock.t += 30
    state.tick()
    assert state.remaining_seconds == 120 * 60 - 120

    state.reset_session()
    assert state.mode == "ready" and state.remaining_seconds == 120 * 60


def test_the_timer_reaching_zero_completes_the_session(sessions, clock):
    state = ready_state(sessions)
    state.start_session()
    clock.t += 120 * 60 + 5
    state.tick()
    assert state.mode == "complete" and state.remaining_seconds == 0 and state.clock == "00:00"
    assert state.completed_minutes == 120


def test_break_uses_the_plans_break_length_then_moves_on(sessions, clock):
    state = ready_state(sessions)
    state.start_session()
    clock.t += 120 * 60
    state.tick()
    state.take_break()
    assert state.mode == "break"
    assert state.total_seconds == state.remaining_seconds == DEFAULT_BREAK_MINUTES * 60
    clock.t += DEFAULT_BREAK_MINUTES * 60
    state.tick()
    assert state.mode == "break_over"
    # Moving on skips the finished session even though its block is still "now".
    state._apply(sessions, has_plan=True, now_minute=16 * 60 + 30, after="Math")
    assert state.mode == "none" and state.next_label == "CS"


def test_reload_while_running_keeps_the_running_session(sessions, clock):
    state = ready_state(sessions)
    state.start_session()
    clock.t += 60
    state._apply(sessions, has_plan=True, now_minute=16 * 60 + 31)     # a page load mid-session
    state.tick()
    assert state.mode == "running" and state.remaining_seconds == 120 * 60 - 60
