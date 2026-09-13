"""
tests/test_focus_api.py
The focus API: the current and next study session from the student's
stored plan, and recording that a session was completed without
touching the assignment or the plan. The clock is under test control.
"""

from datetime import date, datetime, timedelta

import pytest
from starlette.testclient import TestClient

import storage
from api import auth, focus
from api.main import create_api

TODAY = date.today()


def days(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def weekday(n: int) -> str:
    return (TODAY + timedelta(days=n)).strftime("%A").upper()


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "focus_api.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(create_api())


@pytest.fixture
def clock(monkeypatch):
    """Set the server's idea of 'now' to a time of day on TODAY."""
    def at(hour: int, minute: int = 0):
        fixed = datetime.combine(TODAY, datetime.min.time()).replace(hour=hour, minute=minute)
        monkeypatch.setattr(focus, "_now", lambda: fixed)
        return fixed
    return at


def student(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "a long enough password"})
    token = client.post("/api/auth/login", json={"email": email, "password": "a long enough password"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ana(client):
    return student(client, "ana@example.com")


@pytest.fixture
def ben(client):
    return student(client, "ben@example.com")


def seed_and_plan(client, headers):
    """Today 4-6 PM and 7-8 PM; Math 2h due day 3, CS 1h due day 4 -> Math 4-6, CS 7-8 today."""
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 16, "end_hour": 18}, headers=headers)
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 19, "end_hour": 20}, headers=headers)
    client.post("/api/assignments", json={"name": "Math", "subject": "Mathematics", "due_date": days(3),
                                          "estimated_hours": 2, "priority": "HIGH"}, headers=headers)
    client.post("/api/assignments", json={"name": "CS", "subject": "Computer Science", "due_date": days(4),
                                          "estimated_hours": 1}, headers=headers)
    plan = client.post("/api/plan/generate", headers=headers).json()
    assert [b["label"] for b in plan["days"][0]["blocks"]] == ["Math", "CS"]
    return plan


# ---------- Authentication ----------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/focus/current"), ("GET", "/api/focus/next"), ("POST", "/api/focus/complete"),
])
def test_every_focus_endpoint_needs_a_login(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"Authorization": "Bearer nonsense"}).status_code == 401


# ---------- Current session ----------

def test_current_session_is_the_block_containing_now(client, ana, clock):
    seed_and_plan(client, ana)
    clock(16, 47)
    r = client.get("/api/focus/current", headers=ana)
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True and body["reason"] is None
    s = body["session"]
    assert (s["assignment"], s["subject"], s["date"], s["start"], s["end"]) == ("Math", "Mathematics", days(0), "16:00", "18:00")
    assert s["duration_minutes"] == 120 and s["remaining_minutes"] == 73 and s["completed"] is False
    assert isinstance(s["assignment_id"], int)


def test_current_session_changes_with_the_clock(client, ana, clock):
    seed_and_plan(client, ana)
    clock(15, 59)
    assert client.get("/api/focus/current", headers=ana).json()["active"] is False
    clock(16, 0)
    assert client.get("/api/focus/current", headers=ana).json()["session"]["assignment"] == "Math"
    clock(18, 0)                                                        # the end minute is not inside
    assert client.get("/api/focus/current", headers=ana).json()["active"] is False
    clock(19, 30)
    assert client.get("/api/focus/current", headers=ana).json()["session"]["assignment"] == "CS"
    clock(20, 5)
    assert client.get("/api/focus/current", headers=ana).json() == {"active": False, "session": None, "reason": "nothing_now"}


def test_a_break_is_never_a_session(client, ana, clock):
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 16, "end_hour": 18}, headers=ana)
    client.post("/api/assignments", json={"name": "A", "subject": "A", "due_date": days(2), "estimated_hours": 1, "priority": "HIGH"}, headers=ana)
    client.post("/api/assignments", json={"name": "B", "subject": "B", "due_date": days(2), "estimated_hours": 0.5}, headers=ana)
    plan = client.post("/api/plan/generate", headers=ana).json()
    assert [b["label"] for b in plan["days"][0]["blocks"]] == ["A", "Break", "B"]
    clock(17, 5)                                                        # inside the 5:00-5:15 break
    assert client.get("/api/focus/current", headers=ana).json()["active"] is False
    assert client.get("/api/focus/next", headers=ana).json()["session"]["assignment"] == "B"


def test_no_plan_and_a_stale_plan_are_sensible_answers(client, ana, clock):
    clock(16, 30)
    assert client.get("/api/focus/current", headers=ana).json() == {"active": False, "session": None, "reason": "no_plan"}
    assert client.get("/api/focus/next", headers=ana).json() == {"session": None, "reason": "no_plan"}
    seed_and_plan(client, ana)
    assert client.get("/api/focus/current", headers=ana).json()["active"] is True
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    client.put(f"/api/assignments/{math['id']}", json={**math, "estimated_hours": 3}, headers=ana)
    assert client.get("/api/focus/current", headers=ana).json() == {"active": False, "session": None, "reason": "plan_stale"}
    assert client.get("/api/focus/next", headers=ana).json() == {"session": None, "reason": "plan_stale"}


# ---------- Next session ----------

def test_next_session_after_the_current_one_or_from_now(client, ana, clock):
    seed_and_plan(client, ana)
    clock(16, 30)
    n = client.get("/api/focus/next", headers=ana).json()["session"]
    assert (n["assignment"], n["date"], n["start"], n["end"], n["duration_minutes"]) == ("CS", days(0), "19:00", "20:00", 60)
    clock(18, 30)                                                        # between blocks: no current, CS next
    assert client.get("/api/focus/current", headers=ana).json()["active"] is False
    assert client.get("/api/focus/next", headers=ana).json()["session"]["assignment"] == "CS"
    clock(19, 30)
    assert client.get("/api/focus/next", headers=ana).json() == {"session": None, "reason": "nothing_next"}


def test_next_session_can_be_on_a_later_day(client, ana, clock):
    client.post("/api/study-time", json={"weekday": weekday(2), "start_hour": 9, "end_hour": 11}, headers=ana)
    client.post("/api/assignments", json={"name": "Essay", "subject": "English", "due_date": days(5),
                                          "estimated_hours": 2}, headers=ana)
    client.post("/api/plan/generate", headers=ana)
    clock(12, 0)
    n = client.get("/api/focus/next", headers=ana).json()["session"]
    assert (n["assignment"], n["date"], n["start"]) == ("Essay", days(2), "09:00")


# ---------- Isolation ----------

def test_a_student_only_sees_their_own_sessions(client, ana, ben, clock):
    seed_and_plan(client, ana)
    clock(16, 30)
    assert client.get("/api/focus/current", headers=ana).json()["session"]["assignment"] == "Math"
    assert client.get("/api/focus/current", headers=ben).json() == {"active": False, "session": None, "reason": "no_plan"}
    assert client.get("/api/focus/next", headers=ben).json()["session"] is None


# ---------- Completing a session ----------

def test_completing_the_current_session_records_it_without_touching_the_plan(client, ana, clock):
    seed_and_plan(client, ana)
    clock(17, 55)
    r = client.post("/api/focus/complete", headers=ana)                 # no body: the current session
    assert r.status_code == 200
    body = r.json()
    assert body["recorded"] is True and body["already_recorded"] is False
    assert (body["session"]["assignment"], body["session"]["completed"]) == ("Math", True)
    assert body["assignment"] == {"id": body["session"]["assignment_id"], "name": "Math", "required_hours": 2.0,
                                  "done_hours": 2.0, "done_percent": 100}
    # The assignment row and the plan are untouched.
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    assert math["completed"] is False
    assert client.get("/api/plan", headers=ana).json()["fresh"] is True
    # The current session now reads as completed, and next moves on.
    assert client.get("/api/focus/current", headers=ana).json()["session"]["completed"] is True
    assert client.get("/api/focus/next", headers=ana).json()["session"]["assignment"] == "CS"


def test_completing_by_block_identity(client, ana, clock):
    seed_and_plan(client, ana)
    clock(12, 0)                                                         # nothing is on, so name the block
    r = client.post("/api/focus/complete", json={"date": days(0), "start": "19:00", "end": "20:00"}, headers=ana)
    assert r.status_code == 200 and r.json()["session"]["assignment"] == "CS"
    assert r.json()["assignment"]["done_hours"] == 1.0
    uid = client.get("/api/me", headers=ana).json()["id"]
    rows = storage.list_session_completions(uid)
    assert [(c.date, c.start_minute, c.end_minute, c.minutes) for c in rows] == [(days(0), 19 * 60, 20 * 60, 60)]


def test_completing_twice_is_idempotent(client, ana, clock):
    seed_and_plan(client, ana)
    clock(17, 0)
    client.post("/api/focus/complete", headers=ana)
    r = client.post("/api/focus/complete", headers=ana)
    assert r.status_code == 200 and r.json()["already_recorded"] is True
    uid = client.get("/api/me", headers=ana).json()["id"]
    assert len(storage.list_session_completions(uid)) == 1
    assert r.json()["assignment"]["done_hours"] == 2.0


@pytest.mark.parametrize("body", [
    {"date": "2026-01-01", "start": "16:00", "end": "18:00"},          # not in the plan
    {"date": None, "start": "16:00", "end": "18:00"},
    {"date": "today", "start": "16:00", "end": "18:00"},
    {"date": "2026-09-13", "start": "4 PM", "end": "6 PM"},
])
def test_completing_a_block_that_is_not_in_the_plan_is_404_or_400(client, ana, clock, body):
    seed_and_plan(client, ana)
    clock(12, 0)
    if body["date"] == "2026-01-01":
        assert client.post("/api/focus/complete", json=body, headers=ana).status_code == 404
    else:
        assert client.post("/api/focus/complete", json=body, headers=ana).status_code == 400


def test_completing_with_nothing_on_and_no_body_is_404(client, ana, clock):
    seed_and_plan(client, ana)
    clock(12, 0)
    r = client.post("/api/focus/complete", headers=ana)
    assert r.status_code == 404


def test_cannot_complete_another_students_session(client, ana, ben, clock):
    seed_and_plan(client, ana)
    clock(16, 30)
    r = client.post("/api/focus/complete", json={"date": days(0), "start": "16:00", "end": "18:00"}, headers=ben)
    assert r.status_code == 404
    uid = client.get("/api/me", headers=ana).json()["id"]
    assert storage.list_session_completions(uid) == []


def test_completing_without_a_fresh_plan_is_refused(client, ana, clock):
    seed_and_plan(client, ana)
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    client.put(f"/api/assignments/{math['id']}", json={**math, "estimated_hours": 3}, headers=ana)
    clock(16, 30)
    r = client.post("/api/focus/complete", headers=ana)
    assert r.status_code == 409 and "regenerate" in r.json()["error"].lower()


# ---------- Progress ----------

def test_completed_sessions_show_up_in_progress_as_hours_done(client, ana, clock):
    seed_and_plan(client, ana)
    before = client.get("/api/plan/progress", headers=ana).json()
    assert before["done_hours"] == 0.0 and before["sessions_completed"] == 0
    assert all(a["done_hours"] == 0.0 and a["done_percent"] == 0 for a in before["assignments"])
    clock(17, 0)
    client.post("/api/focus/complete", headers=ana)
    after = client.get("/api/plan/progress", headers=ana).json()
    assert after["fresh"] is True                                        # nothing about the plan changed
    assert after["done_hours"] == 2.0 and after["sessions_completed"] == 1
    by_name = {a["name"]: a for a in after["assignments"]}
    assert (by_name["Math"]["done_hours"], by_name["Math"]["done_percent"]) == (2.0, 100)
    assert (by_name["CS"]["done_hours"], by_name["CS"]["done_percent"]) == (0.0, 0)
    assert by_name["Math"]["scheduled_hours"] == 2.0                    # the engine's numbers are unchanged


def test_hours_done_survive_a_regenerated_plan(client, ana, clock):
    """Studied time is studied time: it stays with the assignment when the plan is rebuilt."""
    seed_and_plan(client, ana)
    clock(17, 0)
    client.post("/api/focus/complete", headers=ana)
    client.post("/api/study-time", json={"weekday": weekday(1), "start_hour": 16, "end_hour": 18}, headers=ana)
    client.post("/api/plan/generate", headers=ana)
    after = client.get("/api/plan/progress", headers=ana).json()
    assert {a["name"]: a["done_hours"] for a in after["assignments"]} == {"Math": 2.0, "CS": 0.0}


# ---------- Storage underneath ----------

def test_session_completion_storage_is_per_student_and_unique_per_block():
    ana = storage.add_user("ana@example.com")
    ben = storage.add_user("ben@example.com")
    first = storage.add_session_completion(ana, 7, "2026-09-13", 16 * 60, 18 * 60)
    again = storage.add_session_completion(ana, 7, "2026-09-13", 16 * 60, 18 * 60)
    assert first is True and again is False
    storage.add_session_completion(ana, 8, "2026-09-13", 19 * 60, 20 * 60)
    assert [(c.assignment_id, c.minutes) for c in storage.list_session_completions(ana)] == [(7, 120), (8, 60)]
    assert storage.list_session_completions(ben) == []
    assert storage.done_minutes_by_assignment(ana) == {7: 120, 8: 60}
    assert storage.done_minutes_by_assignment(ben) == {}
