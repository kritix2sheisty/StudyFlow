"""
tests/test_history_api.py
Session history over HTTP: every study block the student recorded,
newest first, with the assignment's name and subject and the minutes,
plus what the phone's History and Progress screens need computed once
on the server: minutes per day and per subject, the current streak,
and today's planned minutes against today's done minutes.
"""

from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

import storage
from api import auth, history
from api.main import create_api
from models import Assignment, Priority

TODAY = date.today()                                                    # the engine plans from the real clock, so history's clock matches it


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    storage.set_db_path(tmp_path / "history_api.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    monkeypatch.setattr(history, "_today", lambda: TODAY)
    yield


@pytest.fixture
def client():
    return TestClient(create_api())


def student(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "a long enough password"})
    token = client.post("/api/auth/login", json={"email": email, "password": "a long enough password"}).json()["token"]
    uid = client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]
    return {"Authorization": f"Bearer {token}"}, uid


def seed(uid: str):
    """Math and Physics assignments; four recorded sessions over the last three days."""
    math = storage.add_assignment(uid, Assignment(name="Math IA", subject="Mathematics", due_date=TODAY + timedelta(days=5),
                                                  estimated_hours=4, priority=Priority.HIGH))
    physics = storage.add_assignment(uid, Assignment(name="Lab report", subject="Physics", due_date=TODAY + timedelta(days=6),
                                                     estimated_hours=2))
    storage.add_session_completion(uid, math, day(-2), 16 * 60, 17 * 60)          # 60 min, two days ago
    storage.add_session_completion(uid, physics, day(-1), 16 * 60, 16 * 60 + 30)   # 30 min, yesterday
    storage.add_session_completion(uid, math, day(0), 9 * 60, 9 * 60 + 45)         # 45 min, today
    storage.add_session_completion(uid, physics, day(0), 16 * 60, 17 * 60)         # 60 min, today
    return math, physics


def test_history_needs_a_login(client):
    assert client.get("/api/focus/history").status_code == 401


def test_a_new_student_has_an_empty_history(client):
    ana, _ = student(client, "ana@example.com")
    r = client.get("/api/focus/history", headers=ana)
    assert r.status_code == 200
    body = r.json()
    assert body["sessions"] == [] and body["minutes"] == 0 and body["sessions_count"] == 0
    assert body["streak_days"] == 0 and body["by_subject"] == []
    assert len(body["by_day"]) == 7 and all(d["minutes"] == 0 for d in body["by_day"])
    assert body["today"] == {"minutes": 0, "sessions": 0, "planned_minutes": 0, "planned_sessions": 0}


def test_sessions_are_listed_newest_first_with_name_subject_and_minutes(client):
    ana, uid = student(client, "ana@example.com")
    math, physics = seed(uid)
    body = client.get("/api/focus/history", headers=ana).json()
    assert [(s["assignment"], s["subject"], s["date"], s["start"], s["end"], s["minutes"]) for s in body["sessions"]] == [
        ("Lab report", "Physics", day(0), "16:00", "17:00", 60),
        ("Math IA", "Mathematics", day(0), "09:00", "09:45", 45),
        ("Lab report", "Physics", day(-1), "16:00", "16:30", 30),
        ("Math IA", "Mathematics", day(-2), "16:00", "17:00", 60),
    ]
    assert body["sessions"][0]["assignment_id"] == physics and body["sessions"][1]["assignment_id"] == math
    assert all(isinstance(s["id"], int) and s["completed_at"] for s in body["sessions"])
    assert body["minutes"] == 195 and body["sessions_count"] == 4


def test_the_window_covers_the_last_days_including_today(client):
    ana, uid = student(client, "ana@example.com")
    math, _ = seed(uid)
    storage.add_session_completion(uid, math, day(-7), 10 * 60, 11 * 60)          # eight days ago: outside a 7-day window
    body = client.get("/api/focus/history", headers=ana).json()
    assert body["days"] == 7 and body["from"] == day(-6) and body["to"] == day(0)
    assert body["sessions_count"] == 4
    assert [d["date"] for d in body["by_day"]] == [day(n) for n in range(-6, 1)]
    assert [(d["minutes"], d["sessions"]) for d in body["by_day"]][-3:] == [(60, 1), (30, 1), (105, 2)]
    wider = client.get("/api/focus/history?days=30", headers=ana).json()
    assert wider["sessions_count"] == 5 and len(wider["by_day"]) == 30


@pytest.mark.parametrize("days", ["0", "-1", "91", "week", ""])
def test_days_must_be_a_whole_number_from_1_to_90(client, days):
    ana, _ = student(client, "ana@example.com")
    r = client.get(f"/api/focus/history?days={days}", headers=ana)
    assert r.status_code == 400
    assert r.json() == {"error": "Give days as a whole number from 1 to 90."}


def test_minutes_by_subject_largest_first(client):
    ana, uid = student(client, "ana@example.com")
    seed(uid)
    body = client.get("/api/focus/history", headers=ana).json()
    assert body["by_subject"] == [{"subject": "Mathematics", "minutes": 105, "sessions": 2},
                                  {"subject": "Physics", "minutes": 90, "sessions": 2}]


def test_streak_counts_consecutive_days_back_from_today(client):
    ana, uid = student(client, "ana@example.com")
    seed(uid)                                                           # today, yesterday, two days ago
    assert client.get("/api/focus/history", headers=ana).json()["streak_days"] == 3


def test_streak_is_still_alive_when_today_has_no_session_yet(client):
    ana, uid = student(client, "ana@example.com")
    math, _ = seed(uid)
    conn = storage.get_connection()
    conn.execute("DELETE FROM session_completions WHERE date = ?", (day(0),))
    conn.commit(); conn.close()
    assert client.get("/api/focus/history", headers=ana).json()["streak_days"] == 2


def test_streak_breaks_on_a_missed_day(client):
    ana, uid = student(client, "ana@example.com")
    math, _ = seed(uid)
    conn = storage.get_connection()
    conn.execute("DELETE FROM session_completions WHERE date = ?", (day(-1),))
    conn.commit(); conn.close()
    assert client.get("/api/focus/history", headers=ana).json()["streak_days"] == 1
    conn = storage.get_connection()
    conn.execute("DELETE FROM session_completions WHERE date = ?", (day(0),))
    conn.commit(); conn.close()
    assert client.get("/api/focus/history", headers=ana).json()["streak_days"] == 0


def test_todays_planned_minutes_come_from_a_fresh_plan(client):
    ana, uid = student(client, "ana@example.com")
    weekday = TODAY.strftime("%A").upper()
    client.post("/api/study-time", json={"weekday": weekday, "start_hour": 16, "end_hour": 18}, headers=ana)
    client.post("/api/assignments", json={"name": "Essay", "subject": "English", "due_date": day(3),
                                          "estimated_hours": 2, "priority": "HIGH"}, headers=ana)
    plan = client.post("/api/plan/generate", headers=ana).json()
    assert [b["label"] for b in plan["days"][0]["blocks"]] == ["Essay"] and plan["days"][0]["date"] == day(0)
    essay = client.get("/api/assignments", headers=ana).json()[0]["id"]
    storage.add_session_completion(uid, essay, day(0), 16 * 60, 17 * 60)
    body = client.get("/api/focus/history", headers=ana).json()
    assert body["today"] == {"minutes": 60, "sessions": 1, "planned_minutes": 120, "planned_sessions": 1}
    client.put(f"/api/assignments/{essay}", json={"name": "Essay", "subject": "English", "due_date": day(3),
                                                  "estimated_hours": 3, "priority": "HIGH"}, headers=ana)
    stale = client.get("/api/focus/history", headers=ana).json()
    assert stale["today"]["planned_minutes"] == 0 and stale["today"]["minutes"] == 60


def test_a_session_of_a_deleted_assignment_is_still_history(client):
    ana, uid = student(client, "ana@example.com")
    math, _ = seed(uid)
    storage.delete_assignment(uid, math)
    body = client.get("/api/focus/history", headers=ana).json()
    gone = [s for s in body["sessions"] if s["assignment_id"] == math]
    assert len(gone) == 2 and all(s["assignment"] == "Removed assignment" and s["subject"] == "" for s in gone)
    assert body["minutes"] == 195                                       # the minutes were still studied


def test_history_is_the_students_own(client):
    ana, uid = student(client, "ana@example.com")
    ben, _ = student(client, "ben@example.com")
    seed(uid)
    assert client.get("/api/focus/history", headers=ben).json()["sessions_count"] == 0
