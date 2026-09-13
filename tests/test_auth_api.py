"""
tests/test_auth_api.py
The authentication API: register, login, logout, me, driven through
Starlette's test client against a temporary database. Also the
storage pieces underneath (password hashes, sessions) and the fact
that the API is mounted on the Reflex backend.
"""

from datetime import datetime, timedelta

import pytest
from starlette.testclient import TestClient

import storage
from api import auth, security
from api.main import create_api

EMAIL = "ana@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "auth.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(create_api())


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Register ----------

def test_register_creates_the_user_and_stores_only_a_hash(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == EMAIL and len(body["id"]) == 36
    found = storage.get_user_by_email(EMAIL)
    assert found.id == body["id"]
    assert PASSWORD not in found.password_hash and found.password_hash.startswith("$argon2")
    assert security.verify_password(PASSWORD, found.password_hash)
    assert not security.verify_password("wrong", found.password_hash)


def test_register_normalises_the_email(client):
    r = register(client, email="  Ana@Example.COM ")
    assert r.status_code == 201 and r.json()["email"] == EMAIL


def test_register_twice_is_a_conflict(client):
    assert register(client).status_code == 201
    r = register(client)
    assert r.status_code == 409 and "already registered" in r.json()["error"]


@pytest.mark.parametrize("email,password", [
    ("not-an-email", PASSWORD),
    ("", PASSWORD),
    (EMAIL, "short7c"),
    (EMAIL, ""),
])
def test_register_rejects_bad_input(client, email, password):
    assert register(client, email, password).status_code == 400


def test_register_needs_a_json_object(client):
    assert client.post("/api/auth/register", content=b"nope").status_code == 400
    assert client.post("/api/auth/register", json=["a"]).status_code == 400


# ---------- Login ----------

def test_login_returns_a_token_and_the_database_holds_only_its_hash(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    token, expires_at = r.json()["token"], r.json()["expires_at"]
    session = storage.find_session(security.token_hash(token))
    assert session is not None and session.revoked_at is None
    assert session.expires_at == expires_at
    assert datetime.fromisoformat(expires_at) > datetime.now() + timedelta(days=security.SESSION_DAYS - 1)
    assert storage.find_session(token) is None                  # the raw token is not stored


def test_wrong_password_and_unknown_email_fail_identically(client):
    register(client)
    wrong = login(client, password="not the password")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"error": auth.LOGIN_FAILED}


# ---------- Me ----------

def test_me_returns_the_user_for_a_valid_token(client):
    uid = register(client).json()["id"]
    token = login(client).json()["token"]
    r = client.get("/api/me", headers=bearer(token))
    assert r.status_code == 200
    assert r.json()["id"] == uid and r.json()["email"] == EMAIL and r.json()["created_at"]


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer"},
    {"Authorization": "Bearer nonsense"},
    {"Authorization": "Basic abc"},
])
def test_me_without_a_usable_token_is_unauthorised(client, headers):
    assert client.get("/api/me", headers=headers).status_code == 401


def test_me_with_an_expired_token_is_unauthorised(client):
    uid = register(client).json()["id"]
    token = security.new_token()
    yesterday = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    storage.create_session(uid, security.token_hash(token), yesterday)
    r = client.get("/api/me", headers=bearer(token))
    assert r.status_code == 401 and "expired" in r.json()["error"]


def test_a_valid_call_extends_the_sessions_expiry(client):
    uid = register(client).json()["id"]
    token = security.new_token()
    soon = (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds")
    storage.create_session(uid, security.token_hash(token), soon)
    assert client.get("/api/me", headers=bearer(token)).status_code == 200
    extended = storage.find_session(security.token_hash(token)).expires_at
    assert datetime.fromisoformat(extended) > datetime.now() + timedelta(days=security.SESSION_DAYS - 1)


# ---------- Logout ----------

def test_logout_revokes_the_token_and_a_new_login_works(client):
    register(client)
    token = login(client).json()["token"]
    assert client.post("/api/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/api/me", headers=bearer(token)).status_code == 401
    assert storage.find_session(security.token_hash(token)).revoked_at is not None
    again = login(client).json()["token"]
    assert again != token
    assert client.get("/api/me", headers=bearer(again)).status_code == 200


def test_logout_without_a_token_is_unauthorised(client):
    assert client.post("/api/auth/logout").status_code == 401


# ---------- The token decides whose data it is ----------

def test_the_token_identifies_the_student_whose_rows_storage_serves(client):
    from datetime import date
    from models import Assignment, Priority
    ana = register(client, "ana@example.com").json()["id"]
    ben = register(client, "ben@example.com").json()["id"]
    storage.add_assignment(ana, Assignment(name="Ana's", subject="A", due_date=date(2026, 9, 30), estimated_hours=1, priority=Priority.LOW))
    storage.add_assignment(ben, Assignment(name="Ben's", subject="B", due_date=date(2026, 9, 30), estimated_hours=1, priority=Priority.LOW))
    token = login(client, "ben@example.com").json()["token"]
    who = client.get("/api/me", headers=bearer(token)).json()["id"]
    assert who == ben
    assert [a.name for a in storage.list_assignments(who)] == ["Ben's"]


# ---------- Rate limiting ----------

def test_eleven_failed_logins_are_rate_limited(client):
    register(client)
    for _ in range(10):
        assert login(client, password="wrong password").status_code == 401
    r = login(client, password="wrong password")
    assert r.status_code == 429


def test_the_login_limit_is_per_email_as_well_as_per_client(client):
    register(client)
    register(client, "ben@example.com")
    auth.login_limiter.reset()
    for _ in range(10):
        auth.login_limiter.allow("email:" + EMAIL)               # ana's email is exhausted
    assert login(client).status_code == 429
    assert login(client, "ben@example.com").status_code == 200   # ben is unaffected


def test_registration_is_rate_limited(client):
    for i in range(10):
        assert register(client, f"s{i}@example.com").status_code == 201
    assert register(client, "s10@example.com").status_code == 429


# ---------- Storage underneath ----------

def test_sessions_can_be_created_found_revoked_and_touched():
    uid = storage.add_user(EMAIL)
    digest = security.token_hash("abc")
    storage.create_session(uid, digest, "2026-12-01T00:00:00")
    s = storage.find_session(digest)
    assert (s.user_id, s.expires_at, s.revoked_at) == (uid, "2026-12-01T00:00:00", None)
    storage.touch_session(digest, "2026-12-31T00:00:00")
    assert storage.find_session(digest).expires_at == "2026-12-31T00:00:00"
    storage.revoke_session(digest)
    assert storage.find_session(digest).revoked_at is not None
    assert storage.find_session("missing") is None


def test_the_built_in_student_has_no_password_and_cannot_log_in(client):
    found = storage.get_user_by_email(storage.DEFAULT_USER_EMAIL)
    assert found is not None and found.password_hash is None
    assert login(client, storage.DEFAULT_USER_EMAIL, "anything at all").status_code == 401


# ---------- Mounted on the Reflex backend ----------

def test_the_api_is_mounted_on_the_reflex_app():
    import StudyFlow.StudyFlow as page
    mounted = page.app.api_transformer
    assert mounted is not None
    c = TestClient(mounted)
    assert c.get("/api/health").json() == {"status": "ok"}
    assert c.get("/api/me").status_code == 401                      # answered by the API, not a 404
