"""
tests/test_assignments_api.py
The assignments API: a logged-in student can manage only their own
assignments. Driven through Starlette's test client against a
temporary database, with two registered students.
"""

from datetime import date

import pytest
from starlette.testclient import TestClient

import storage
from api import auth
from api.main import create_api
from models import Assignment, Priority

ESSAY = {"name": "History Essay", "subject": "History", "due_date": "2026-09-20",
         "estimated_hours": 2.5, "priority": "HIGH"}


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "assignments_api.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(create_api())


def student(client, email):
    """Register and log in; return the bearer headers."""
    client.post("/api/auth/register", json={"email": email, "password": "a long enough password"})
    token = client.post("/api/auth/login", json={"email": email, "password": "a long enough password"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ana(client):
    return student(client, "ana@example.com")


@pytest.fixture
def ben(client):
    return student(client, "ben@example.com")


# ---------- Authentication ----------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/assignments"), ("POST", "/api/assignments"), ("PUT", "/api/assignments/1"),
    ("DELETE", "/api/assignments/1"), ("POST", "/api/assignments/1/complete"),
])
def test_every_assignment_endpoint_needs_a_login(client, method, path):
    assert client.request(method, path, json=ESSAY).status_code == 401
    assert client.request(method, path, json=ESSAY, headers={"Authorization": "Bearer nonsense"}).status_code == 401


# ---------- Create and list ----------

def test_create_returns_the_stored_assignment(client, ana):
    r = client.post("/api/assignments", json=ESSAY, headers=ana)
    assert r.status_code == 201
    body = r.json()
    assert body == {"id": body["id"], **ESSAY, "completed": False}
    assert isinstance(body["id"], int)


def test_priority_defaults_to_medium(client, ana):
    r = client.post("/api/assignments", json={k: v for k, v in ESSAY.items() if k != "priority"}, headers=ana)
    assert r.status_code == 201 and r.json()["priority"] == "MEDIUM"


def test_list_returns_only_the_logged_in_students_assignments_soonest_first(client, ana, ben):
    client.post("/api/assignments", json={**ESSAY, "name": "Ana later", "due_date": "2026-09-25"}, headers=ana)
    client.post("/api/assignments", json={**ESSAY, "name": "Ana sooner", "due_date": "2026-09-18"}, headers=ana)
    client.post("/api/assignments", json={**ESSAY, "name": "Ben's"}, headers=ben)
    assert [a["name"] for a in client.get("/api/assignments", headers=ana).json()] == ["Ana sooner", "Ana later"]
    assert [a["name"] for a in client.get("/api/assignments", headers=ben).json()] == ["Ben's"]


def test_list_is_empty_for_a_new_student(client, ana):
    assert client.get("/api/assignments", headers=ana).json() == []


@pytest.mark.parametrize("bad", [
    {**ESSAY, "name": ""},
    {**ESSAY, "name": "   "},
    {**ESSAY, "subject": ""},
    {**ESSAY, "due_date": "20/09/2026"},
    {**ESSAY, "due_date": ""},
    {**ESSAY, "estimated_hours": "two"},
    {**ESSAY, "estimated_hours": -1},
    {**ESSAY, "priority": "URGENT"},
    {**ESSAY, "completed": "yes"},
    {},
])
def test_create_rejects_bad_data(client, ana, bad):
    r = client.post("/api/assignments", json=bad, headers=ana)
    assert r.status_code == 400 and r.json()["error"]


def test_create_needs_a_json_object(client, ana):
    assert client.post("/api/assignments", content=b"nope", headers=ana).status_code == 400
    assert client.post("/api/assignments", json=[1], headers=ana).status_code == 400


# ---------- Update ----------

def test_update_own_assignment(client, ana):
    aid = client.post("/api/assignments", json=ESSAY, headers=ana).json()["id"]
    r = client.put(f"/api/assignments/{aid}", json={**ESSAY, "estimated_hours": 4, "priority": "LOW"}, headers=ana)
    assert r.status_code == 200
    assert (r.json()["estimated_hours"], r.json()["priority"], r.json()["id"]) == (4, "LOW", aid)
    stored = storage.list_assignments(client.get("/api/me", headers=ana).json()["id"])[0]
    assert (stored.estimated_hours, stored.priority) == (4, Priority.LOW)


def test_update_keeps_completed_unless_told_otherwise(client, ana):
    aid = client.post("/api/assignments", json=ESSAY, headers=ana).json()["id"]
    client.post(f"/api/assignments/{aid}/complete", headers=ana)
    r = client.put(f"/api/assignments/{aid}", json={**ESSAY, "name": "Renamed"}, headers=ana)
    assert r.json()["completed"] is True and r.json()["name"] == "Renamed"
    r = client.put(f"/api/assignments/{aid}", json={**ESSAY, "completed": False}, headers=ana)
    assert r.json()["completed"] is False


def test_cannot_update_another_students_assignment(client, ana, ben):
    bens = client.post("/api/assignments", json=ESSAY, headers=ben).json()["id"]
    r = client.put(f"/api/assignments/{bens}", json={**ESSAY, "name": "Hacked"}, headers=ana)
    assert r.status_code == 404                                   # not "forbidden": Ana never learns it exists
    assert client.get("/api/assignments", headers=ben).json()[0]["name"] == "History Essay"


def test_update_rejects_bad_data_and_unknown_ids(client, ana):
    aid = client.post("/api/assignments", json=ESSAY, headers=ana).json()["id"]
    assert client.put(f"/api/assignments/{aid}", json={**ESSAY, "due_date": "soon"}, headers=ana).status_code == 400
    assert client.put("/api/assignments/999", json=ESSAY, headers=ana).status_code == 404
    assert client.put("/api/assignments/abc", json=ESSAY, headers=ana).status_code == 404


# ---------- Delete ----------

def test_delete_own_assignment(client, ana):
    aid = client.post("/api/assignments", json=ESSAY, headers=ana).json()["id"]
    assert client.delete(f"/api/assignments/{aid}", headers=ana).status_code == 204
    assert client.get("/api/assignments", headers=ana).json() == []
    assert client.delete(f"/api/assignments/{aid}", headers=ana).status_code == 404   # already gone


def test_cannot_delete_another_students_assignment(client, ana, ben):
    bens = client.post("/api/assignments", json=ESSAY, headers=ben).json()["id"]
    assert client.delete(f"/api/assignments/{bens}", headers=ana).status_code == 404
    assert len(client.get("/api/assignments", headers=ben).json()) == 1


# ---------- Complete ----------

def test_complete_own_assignment_and_the_storage_semantics_hold(client, ana):
    aid = client.post("/api/assignments", json=ESSAY, headers=ana).json()["id"]
    r = client.post(f"/api/assignments/{aid}/complete", headers=ana)
    assert r.status_code == 200 and r.json()["completed"] is True
    # Completed work leaves the active list but stays stored, as in the app.
    assert client.get("/api/assignments", headers=ana).json() == []
    assert [a["name"] for a in client.get("/api/assignments?status=completed", headers=ana).json()] == ["History Essay"]
    assert len(client.get("/api/assignments?status=all", headers=ana).json()) == 1
    # And it can be reopened.
    r = client.post(f"/api/assignments/{aid}/complete", json={"completed": False}, headers=ana)
    assert r.json()["completed"] is False
    assert len(client.get("/api/assignments", headers=ana).json()) == 1


def test_cannot_complete_another_students_assignment(client, ana, ben):
    bens = client.post("/api/assignments", json=ESSAY, headers=ben).json()["id"]
    assert client.post(f"/api/assignments/{bens}/complete", headers=ana).status_code == 404
    assert client.get("/api/assignments", headers=ben).json()[0]["completed"] is False


def test_complete_unknown_assignment_is_404(client, ana):
    assert client.post("/api/assignments/999/complete", headers=ana).status_code == 404


def test_bad_status_filter_is_400(client, ana):
    assert client.get("/api/assignments?status=done", headers=ana).status_code == 400


# ---------- The API and the app agree ----------

def test_the_api_writes_what_the_web_app_reads(client, ana):
    """A row created through the API is exactly what storage gives the Reflex app."""
    body = client.post("/api/assignments", json=ESSAY, headers=ana).json()
    uid = client.get("/api/me", headers=ana).json()["id"]
    stored = storage.list_assignments(uid)
    assert stored == [Assignment(id=body["id"], name="History Essay", subject="History", due_date=date(2026, 9, 20),
                                 estimated_hours=2.5, priority=Priority.HIGH, completed=False)]
