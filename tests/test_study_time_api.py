"""
tests/test_study_time_api.py
The study-time API: a logged-in student manages only their own weekly
study slots. Driven through Starlette's test client against a
temporary database, with two registered students.
"""

import pytest
from starlette.testclient import TestClient

import storage
from api import auth
from api.main import create_api
from models import Weekday

WED = {"weekday": "WEDNESDAY", "start_hour": 16, "end_hour": 18}


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "study_time_api.db")
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


@pytest.fixture
def ana(client):
    return student(client, "ana@example.com")


@pytest.fixture
def ben(client):
    return student(client, "ben@example.com")


def user_id(client, headers):
    return client.get("/api/me", headers=headers).json()["id"]


# ---------- Authentication ----------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/study-time"), ("POST", "/api/study-time"), ("DELETE", "/api/study-time/1"),
])
def test_every_study_time_endpoint_needs_a_login(client, method, path):
    assert client.request(method, path, json=WED).status_code == 401
    assert client.request(method, path, json=WED, headers={"Authorization": "Bearer nonsense"}).status_code == 401


# ---------- List and add ----------

def test_list_returns_only_the_logged_in_students_slots_in_week_order(client, ana, ben):
    client.post("/api/study-time", json={"weekday": "FRIDAY", "start_hour": 16, "end_hour": 18}, headers=ana)
    client.post("/api/study-time", json=WED, headers=ana)
    client.post("/api/study-time", json={"weekday": "MONDAY", "start_hour": 9, "end_hour": 11}, headers=ben)
    assert [s["weekday"] for s in client.get("/api/study-time", headers=ana).json()] == ["WEDNESDAY", "FRIDAY"]
    assert [s["weekday"] for s in client.get("/api/study-time", headers=ben).json()] == ["MONDAY"]


def test_list_is_empty_for_a_new_student(client, ana):
    assert client.get("/api/study-time", headers=ana).json() == []


def test_add_returns_the_stored_slot_with_its_length(client, ana):
    r = client.post("/api/study-time", json=WED, headers=ana)
    assert r.status_code == 201
    body = r.json()
    assert body == {"id": body["id"], "weekday": "WEDNESDAY", "start_hour": 16, "end_hour": 18, "hours": 2}
    assert isinstance(body["id"], int)


def test_weekday_is_accepted_in_any_case(client, ana):
    r = client.post("/api/study-time", json={**WED, "weekday": "wednesday"}, headers=ana)
    assert r.status_code == 201 and r.json()["weekday"] == "WEDNESDAY"


@pytest.mark.parametrize("bad,reason", [
    ({**WED, "weekday": "FUNDAY"}, "weekday"),
    ({**WED, "weekday": 2}, "weekday"),
    ({**WED, "start_hour": -1}, "start"),
    ({**WED, "start_hour": 24}, "start"),
    ({**WED, "end_hour": 25}, "end"),
    ({**WED, "start_hour": "four"}, "start"),
    ({**WED, "start_hour": 16.5}, "start"),
    ({**WED, "start_hour": 18, "end_hour": 16}, "after"),          # end before start
    ({**WED, "start_hour": 16, "end_hour": 16}, "after"),          # zero length
    ({"weekday": "WEDNESDAY"}, "hour"),                             # missing hours
    ({"start_hour": 16, "end_hour": 18}, "weekday"),                # missing weekday
    ({}, "weekday"),
])
def test_add_rejects_bad_data(client, ana, bad, reason):
    r = client.post("/api/study-time", json=bad, headers=ana)
    assert r.status_code == 400 and reason in r.json()["error"].lower()


def test_add_needs_a_json_object(client, ana):
    assert client.post("/api/study-time", content=b"nope", headers=ana).status_code == 400
    assert client.post("/api/study-time", json=[1], headers=ana).status_code == 400


# ---------- Delete ----------

def test_delete_own_slot(client, ana):
    sid = client.post("/api/study-time", json=WED, headers=ana).json()["id"]
    assert client.delete(f"/api/study-time/{sid}", headers=ana).status_code == 204
    assert client.get("/api/study-time", headers=ana).json() == []


def test_cannot_delete_another_students_slot(client, ana, ben):
    bens = client.post("/api/study-time", json=WED, headers=ben).json()["id"]
    assert client.delete(f"/api/study-time/{bens}", headers=ana).status_code == 404
    assert len(client.get("/api/study-time", headers=ben).json()) == 1          # Ben's data untouched


def test_delete_unknown_or_malformed_id_is_404(client, ana):
    assert client.delete("/api/study-time/999", headers=ana).status_code == 404
    assert client.delete("/api/study-time/abc", headers=ana).status_code == 404
    sid = client.post("/api/study-time", json=WED, headers=ana).json()["id"]
    client.delete(f"/api/study-time/{sid}", headers=ana)
    assert client.delete(f"/api/study-time/{sid}", headers=ana).status_code == 404  # already gone


# ---------- The API and storage agree ----------

def test_a_slot_created_through_the_api_is_what_storage_gives_the_web_app(client, ana, ben):
    body = client.post("/api/study-time", json=WED, headers=ana).json()
    stored = storage.list_time_slots(user_id(client, ana))
    assert [(s.id, s.weekday, s.start_hour, s.end_hour) for s in stored] == [(body["id"], Weekday.WEDNESDAY, 16, 18)]
    assert storage.list_time_slots(user_id(client, ben)) == []
