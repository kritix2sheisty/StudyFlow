"""
tests/test_account_api.py
Claiming the pre-account data: the built-in student's assignments,
study time, plan and completed sessions go to the first account that
asks, once, and never to anyone after that.
"""

from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

import storage
from api import auth
from api.main import create_api
from models import Assignment, Priority, TimeSlot, Weekday

ME = storage.DEFAULT_USER_ID


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "account_api.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(create_api())


def student(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "a long enough password"})
    token = client.post("/api/auth/login", json={"email": email, "password": "a long enough password"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def seed_local_data():
    storage.add_assignment(ME, Assignment(name="Old essay", subject="English", due_date=date.today() + timedelta(days=3),
                                          estimated_hours=2, priority=Priority.HIGH))
    storage.add_assignment(ME, Assignment(name="Old lab", subject="Biology", due_date=date.today() + timedelta(days=5),
                                          estimated_hours=1, completed=True))
    storage.add_time_slot(ME, TimeSlot(weekday=Weekday.MONDAY, start_hour=16, end_hour=18))
    storage.save_plan(ME, "fp", "2026-09-12T20:00:00", '{"days": []}')
    storage.add_session_completion(ME, 1, date.today().isoformat(), 16 * 60, 18 * 60)


def test_endpoints_need_a_login(client):
    assert client.get("/api/account/local-data").status_code == 401
    assert client.post("/api/account/import-local").status_code == 401


def test_nothing_to_import_on_a_fresh_installation(client):
    ana = student(client, "ana@example.com")
    r = client.get("/api/account/local-data", headers=ana)
    assert r.status_code == 200
    assert r.json() == {"available": False, "assignments": 0, "time_slots": 0, "plans": 0, "session_completions": 0}
    assert client.post("/api/account/import-local", headers=ana).json()["imported"] is False


def test_local_data_is_reported_then_claimed_once(client):
    seed_local_data()
    ana = student(client, "ana@example.com")
    ben = student(client, "ben@example.com")
    r = client.get("/api/account/local-data", headers=ana).json()
    assert r == {"available": True, "assignments": 2, "time_slots": 1, "plans": 1, "session_completions": 1}
    assert client.get("/api/account/local-data", headers=ben).json()["available"] is True   # nobody has claimed it yet

    moved = client.post("/api/account/import-local", headers=ana).json()
    assert moved == {"imported": True, "assignments": 2, "time_slots": 1, "plans": 1, "session_completions": 1}

    # Ana now owns it, through the ordinary endpoints.
    names = [a["name"] for a in client.get("/api/assignments?status=all", headers=ana).json()]
    assert sorted(names) == ["Old essay", "Old lab"]
    assert len(client.get("/api/study-time", headers=ana).json()) == 1
    assert client.get("/api/plan/progress", headers=ana).json()["sessions_completed"] == 1

    # The built-in student holds nothing; Ben sees nothing and cannot claim it.
    assert client.get("/api/account/local-data", headers=ben).json()["available"] is False
    assert client.post("/api/account/import-local", headers=ben).json()["imported"] is False
    assert client.get("/api/assignments?status=all", headers=ben).json() == []
    assert storage.list_assignments(ME) == [] and storage.list_time_slots(ME) == []


def test_a_claimant_with_their_own_plan_keeps_it(client):
    seed_local_data()
    ana = student(client, "ana@example.com")
    client.post("/api/study-time", json={"weekday": date.today().strftime("%A").upper(), "start_hour": 9, "end_hour": 11}, headers=ana)
    client.post("/api/assignments", json={"name": "Mine", "subject": "M", "due_date": (date.today() + timedelta(days=2)).isoformat(),
                                          "estimated_hours": 1}, headers=ana)
    own = client.post("/api/plan/generate", headers=ana).json()
    moved = client.post("/api/account/import-local", headers=ana).json()
    assert moved["plans"] == 0 and moved["assignments"] == 2
    uid = client.get("/api/me", headers=ana).json()["id"]
    assert storage.get_plan(uid).generated_at == own["generated_at"]        # Ana's own plan survived
    assert storage.get_plan(ME) is None                                     # the old plan is gone, not duplicated


def test_claim_storage_refuses_to_move_data_onto_the_built_in_student():
    seed_local_data()
    assert storage.claim_local_data(ME) == {"assignments": 0, "time_slots": 0, "plans": 0, "session_completions": 0}
    assert len(storage.list_assignments(ME)) == 2
