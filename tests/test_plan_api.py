"""
tests/test_plan_api.py
The plan API: generate, read back with freshness, and progress, for
the authenticated student only. The expected numbers come from the
engine itself (study_plan + plan_view), never from a second
scheduler, so the API is proven to be a wrapper and nothing more.
"""

from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

import storage
from api import auth
from api.main import create_api
from StudyFlow import plan_view
from study_plan import generate_study_plan

TODAY = date.today()


def days(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def weekday(n: int) -> str:
    return (TODAY + timedelta(days=n)).strftime("%A").upper()


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "plan_api.db")
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


def seed(client, headers, math_hours=2, physics_hours=5):
    """The mentor's controlled example: two 2h slots on days 0 and 1, Math due day 3, Physics due day 4."""
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 16, "end_hour": 18}, headers=headers)
    client.post("/api/study-time", json={"weekday": weekday(1), "start_hour": 16, "end_hour": 18}, headers=headers)
    client.post("/api/assignments", json={"name": "Math", "subject": "Mathematics", "due_date": days(3),
                                          "estimated_hours": math_hours, "priority": "MEDIUM"}, headers=headers)
    client.post("/api/assignments", json={"name": "Physics", "subject": "Physics", "due_date": days(4),
                                          "estimated_hours": physics_hours, "priority": "HIGH"}, headers=headers)


def engine_plan(client, headers):
    uid = client.get("/api/me", headers=headers).json()["id"]
    assignments = storage.list_assignments(uid, include_completed=False)
    slots = storage.list_time_slots(uid)
    return generate_study_plan(assignments, slots, today=TODAY), slots


# ---------- Authentication ----------

@pytest.mark.parametrize("method,path", [
    ("POST", "/api/plan/generate"), ("GET", "/api/plan"), ("GET", "/api/plan/progress"),
])
def test_every_plan_endpoint_needs_a_login(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"Authorization": "Bearer nonsense"}).status_code == 401


# ---------- Generation ----------

def test_generate_builds_the_plan_the_engine_would(client, ana):
    seed(client, ana)
    r = client.post("/api/plan/generate", headers=ana)
    assert r.status_code == 200
    body = r.json()
    plan, slots = engine_plan(client, ana)

    assert body["fresh"] is True and body["generated_at"]
    assert body["required_hours"] == plan.required_hours == 7.0
    assert body["scheduled_hours"] == plan.scheduled_hours == 4.0
    assert body["unscheduled_hours"] == plan.unscheduled_hours == 3.0
    assert body["completion_percentage"] == round(plan.completion, 1)

    # The schedule, day by day, block by block, is the engine's.
    expected_days = [
        {"date": day.isoformat(), "label": day.strftime("%A %d %b"),
         "blocks": [{"start": f"{b.start_minute // 60:02d}:{b.start_minute % 60:02d}",
                     "end": f"{b.end_minute // 60:02d}:{b.end_minute % 60:02d}",
                     "time": b.format_time_range(), "label": b.label,
                     "is_break": b.label == "Break"} for b in blocks]}
        for day, blocks in sorted(plan.schedule.by_date.items())
    ]
    assert body["days"] == expected_days
    assert [b["label"] for b in body["days"][0]["blocks"]] == ["Math"]              # soonest due first
    assert [b["label"] for b in body["days"][1]["blocks"]] == ["Physics"]


def test_generated_statuses_and_risks_are_the_analyzers_and_optimizers(client, ana):
    seed(client, ana)
    body = client.post("/api/plan/generate", headers=ana).json()
    plan, slots = engine_plan(client, ana)
    expected = [
        {"id": int(r.id), "name": r.name, "subject": r.subject, "due_date": r.due, "status": r.status,
         "required_hours": float(r.required), "scheduled_hours": float(r.scheduled),
         "remaining_hours": float(r.remaining), "percent": r.percent, "risk": r.risk}
        for r in plan_view.status_rows(plan, slots, TODAY)
    ]
    assert body["assignments"] == expected
    by_name = {a["name"]: a for a in body["assignments"]}
    assert by_name["Math"]["status"] == "COMPLETE" and by_name["Math"]["risk"] == "LOW"
    assert by_name["Physics"]["status"] == "PARTIAL" and by_name["Physics"]["risk"] == "CRITICAL"


def test_generate_with_no_assignments_explains(client, ana):
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 16, "end_hour": 18}, headers=ana)
    r = client.post("/api/plan/generate", headers=ana)
    assert r.status_code == 400 and "assignments" in r.json()["error"]
    assert client.get("/api/plan", headers=ana).json() == {"fresh": False, "plan": None}


def test_generate_with_no_study_time_explains(client, ana):
    client.post("/api/assignments", json={"name": "Math", "subject": "M", "due_date": days(3),
                                          "estimated_hours": 2}, headers=ana)
    r = client.post("/api/plan/generate", headers=ana)
    assert r.status_code == 400 and "study times" in r.json()["error"]


# ---------- Reading the plan back, with freshness ----------

def test_no_plan_yet_is_a_clean_answer_not_an_error(client, ana):
    assert client.get("/api/plan", headers=ana).status_code == 200
    assert client.get("/api/plan", headers=ana).json() == {"fresh": False, "plan": None}


def test_get_plan_returns_the_generated_plan_while_fresh(client, ana):
    seed(client, ana)
    generated = client.post("/api/plan/generate", headers=ana).json()
    r = client.get("/api/plan", headers=ana)
    assert r.status_code == 200 and r.json()["fresh"] is True
    assert r.json()["plan"] == generated


def test_changing_an_assignment_makes_the_plan_stale(client, ana):
    seed(client, ana)
    client.post("/api/plan/generate", headers=ana)
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    client.put(f"/api/assignments/{math['id']}", json={**math, "estimated_hours": 3}, headers=ana)
    assert client.get("/api/plan", headers=ana).json() == {"fresh": False, "plan": None}


def test_completing_or_deleting_an_assignment_makes_the_plan_stale(client, ana):
    seed(client, ana)
    client.post("/api/plan/generate", headers=ana)
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    client.post(f"/api/assignments/{math['id']}/complete", headers=ana)
    assert client.get("/api/plan", headers=ana).json()["fresh"] is False
    client.post("/api/plan/generate", headers=ana)
    assert client.get("/api/plan", headers=ana).json()["fresh"] is True
    physics = client.get("/api/assignments", headers=ana).json()[0]
    client.delete(f"/api/assignments/{physics['id']}", headers=ana)
    assert client.get("/api/plan", headers=ana).json()["fresh"] is False


def test_changing_study_time_makes_the_plan_stale(client, ana):
    seed(client, ana)
    client.post("/api/plan/generate", headers=ana)
    client.post("/api/study-time", json={"weekday": weekday(2), "start_hour": 9, "end_hour": 11}, headers=ana)
    assert client.get("/api/plan", headers=ana).json()["fresh"] is False
    client.post("/api/plan/generate", headers=ana)
    slot = client.get("/api/study-time", headers=ana).json()[0]
    client.delete(f"/api/study-time/{slot['id']}", headers=ana)
    assert client.get("/api/plan", headers=ana).json()["fresh"] is False


def test_unchanged_data_keeps_the_plan_fresh_across_reads(client, ana):
    seed(client, ana)
    client.post("/api/plan/generate", headers=ana)
    for _ in range(3):
        assert client.get("/api/plan", headers=ana).json()["fresh"] is True
    client.get("/api/assignments", headers=ana)                       # reading changes nothing
    assert client.get("/api/plan", headers=ana).json()["fresh"] is True


def test_regenerating_replaces_the_stored_plan(client, ana):
    seed(client, ana)
    first = client.post("/api/plan/generate", headers=ana).json()
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    client.put(f"/api/assignments/{math['id']}", json={**math, "estimated_hours": 1}, headers=ana)
    second = client.post("/api/plan/generate", headers=ana).json()
    assert second["required_hours"] == 6.0 and first["required_hours"] == 7.0
    assert client.get("/api/plan", headers=ana).json()["plan"] == second


# ---------- Progress ----------

def test_progress_matches_the_plan_and_lists_completed_work(client, ana):
    seed(client, ana)
    client.post("/api/assignments", json={"name": "Done already", "subject": "D", "due_date": days(1),
                                          "estimated_hours": 1}, headers=ana)
    done = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Done already")
    client.post(f"/api/assignments/{done['id']}/complete", headers=ana)
    plan = client.post("/api/plan/generate", headers=ana).json()
    r = client.get("/api/plan/progress", headers=ana)
    assert r.status_code == 200
    p = r.json()
    assert p["fresh"] is True
    assert (p["required_hours"], p["scheduled_hours"], p["unscheduled_hours"], p["completion_percentage"]) == \
        (plan["required_hours"], plan["scheduled_hours"], plan["unscheduled_hours"], plan["completion_percentage"])
    assert p["assignments"] == plan["assignments"]                       # completed work is not in the plan
    assert p["completed"] == ["Done already"]                            # but is listed, as on the Progress page
    assert p["active_count"] == 2 and p["completed_count"] == 1


def test_progress_without_a_fresh_plan_shows_no_stale_numbers(client, ana):
    seed(client, ana)
    p = client.get("/api/plan/progress", headers=ana).json()
    assert p["fresh"] is False and p["assignments"] == [] and p["scheduled_hours"] == 0.0
    assert p["required_hours"] == 7.0                                    # what the student has to do, from their data
    client.post("/api/plan/generate", headers=ana)
    math = next(a for a in client.get("/api/assignments", headers=ana).json() if a["name"] == "Math")
    client.put(f"/api/assignments/{math['id']}", json={**math, "estimated_hours": 3}, headers=ana)
    p = client.get("/api/plan/progress", headers=ana).json()
    assert p["fresh"] is False and p["assignments"] == [] and p["required_hours"] == 8.0


# ---------- Isolation ----------

def test_each_student_gets_only_their_own_plan_and_progress(client, ana, ben):
    seed(client, ana)
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 9, "end_hour": 12}, headers=ben)
    client.post("/api/assignments", json={"name": "Ben's essay", "subject": "English", "due_date": days(2),
                                          "estimated_hours": 1, "priority": "LOW"}, headers=ben)
    a_plan = client.post("/api/plan/generate", headers=ana).json()
    b_plan = client.post("/api/plan/generate", headers=ben).json()
    assert {x["name"] for x in a_plan["assignments"]} == {"Math", "Physics"}
    assert {x["name"] for x in b_plan["assignments"]} == {"Ben's essay"}
    assert client.get("/api/plan", headers=ana).json()["plan"] == a_plan
    assert client.get("/api/plan", headers=ben).json()["plan"] == b_plan
    assert [x["name"] for x in client.get("/api/plan/progress", headers=ben).json()["assignments"]] == ["Ben's essay"]


def test_another_students_changes_do_not_touch_my_freshness(client, ana, ben):
    seed(client, ana)
    client.post("/api/plan/generate", headers=ana)
    client.post("/api/study-time", json={"weekday": weekday(0), "start_hour": 9, "end_hour": 12}, headers=ben)
    client.post("/api/assignments", json={"name": "Ben's essay", "subject": "English", "due_date": days(2),
                                          "estimated_hours": 1}, headers=ben)
    assert client.get("/api/plan", headers=ana).json()["fresh"] is True
    assert client.get("/api/plan", headers=ben).json() == {"fresh": False, "plan": None}


def test_a_user_id_in_the_request_is_ignored(client, ana, ben):
    seed(client, ana)
    client.post("/api/plan/generate", headers=ana)
    ana_id = client.get("/api/me", headers=ana).json()["id"]
    r = client.get(f"/api/plan?user_id={ana_id}", headers=ben)
    assert r.json() == {"fresh": False, "plan": None}                    # Ben still gets Ben's (empty) plan
    r = client.post("/api/plan/generate", json={"user_id": ana_id}, headers=ben)
    assert r.status_code == 400                                           # Ben has no data of his own


# ---------- Storage underneath ----------

def test_the_stored_plan_is_json_with_its_fingerprint():
    uid = storage.add_user("ana@example.com")
    assert storage.get_plan(uid) is None
    storage.save_plan(uid, "abc123", "2026-09-12T21:00:00", '{"required_hours": 1.0}')
    stored = storage.get_plan(uid)
    assert (stored.user_id, stored.fingerprint, stored.generated_at) == (uid, "abc123", "2026-09-12T21:00:00")
    assert stored.plan_json == '{"required_hours": 1.0}'
    storage.save_plan(uid, "def456", "2026-09-13T21:00:00", "{}")          # one plan per student: replaced
    assert storage.get_plan(uid).fingerprint == "def456"
    assert storage.get_plan(storage.add_user("ben@example.com")) is None
