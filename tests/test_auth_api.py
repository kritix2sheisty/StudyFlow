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
    auth.reset_limiter.reset()
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

# ---------- Password reset ----------

PUBLIC = "https://studyflow.example"


def smtp_ready(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STUDYFLOW_SMTP_FROM", "StudyFlow <noreply@example.com>")
    monkeypatch.setenv("STUDYFLOW_PUBLIC_URL", PUBLIC)
    monkeypatch.setenv("STUDYFLOW_SMTP_USER", "mailbox")
    monkeypatch.setenv("STUDYFLOW_SMTP_PASSWORD", "secret")


def forgot(client, email=EMAIL):
    return client.post("/api/auth/forgot", json={"email": email})


def reset(client, token, password="a brand new password"):
    return client.post("/api/auth/reset", json={"token": token, "password": password})


def test_forgot_is_unavailable_until_email_is_configured(client, monkeypatch):
    monkeypatch.delenv("STUDYFLOW_SMTP_HOST", raising=False)
    monkeypatch.delenv("STUDYFLOW_SMTP_FROM", raising=False)
    monkeypatch.delenv("STUDYFLOW_PUBLIC_URL", raising=False)
    register(client)
    for email in (EMAIL, "nobody@example.com"):
        r = forgot(client, email)
        assert r.status_code == 503
        assert r.json()["error"] == "Password reset email is not set up yet."
    assert storage.find_password_reset("anything") is None


def test_forgot_for_an_unknown_email_sends_nothing(client, monkeypatch):
    smtp_ready(monkeypatch)
    sent = {}
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: sent.update(to=to, link=link))
    r = forgot(client, "nobody@example.com")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert sent == {}
    conn = storage.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0]
    conn.close()
    assert count == 0


def test_a_user_without_a_password_is_not_emailed(client, monkeypatch):
    smtp_ready(monkeypatch)
    storage.add_user("nopass@example.com")
    sent = {}
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: sent.update(to=to, link=link))
    r = forgot(client, "nopass@example.com")
    assert r.status_code == 200 and sent == {}


def test_forgot_emails_a_link_and_stores_only_the_hash(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    smtp_ready(monkeypatch)
    register(client)
    sent = {}
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: sent.update(to=to, link=link))
    assert forgot(client).status_code == 200
    assert sent["to"] == EMAIL
    token = parse_qs(urlparse(sent["link"]).query)["token"][0]
    assert sent["link"] == f"{PUBLIC}/reset?token={token}"
    assert storage.find_password_reset(token) is None
    stored = storage.find_password_reset(security.token_hash(token))
    assert stored is not None and stored.used_at is None and stored.expires_at
    assert token not in stored.expires_at


def test_reset_changes_the_password_once_and_a_newer_link_replaces_the_old_one(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    smtp_ready(monkeypatch)
    register(client)
    sent = {}
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: sent.update(link=link))

    assert forgot(client).status_code == 200
    first = parse_qs(urlparse(sent["link"]).query)["token"][0]
    assert forgot(client).status_code == 200
    second = parse_qs(urlparse(sent["link"]).query)["token"][0]
    assert first != second
    assert reset(client, first).status_code == 400
    assert reset(client, second, "a brand new password").status_code == 200
    assert reset(client, second, "yet another password").status_code == 400
    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password="a brand new password").status_code == 200


def test_an_expired_reset_link_is_rejected(client):
    uid = register(client).json()["id"]
    digest = security.token_hash("expired-token")
    storage.create_password_reset(uid, digest, "2000-01-01T00:00:00")
    r = reset(client, "expired-token")
    assert r.status_code == 400 and r.json()["error"] == auth.RESET_INVALID
    assert login(client).status_code == 200


def test_reset_logs_out_every_existing_session(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    smtp_ready(monkeypatch)
    register(client)
    old = login(client).json()["token"]
    sent = {}
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: sent.update(link=link))
    forgot(client)
    token = parse_qs(urlparse(sent["link"]).query)["token"][0]
    assert reset(client, token, "a brand new password").status_code == 200
    assert client.get("/api/me", headers=bearer(old)).status_code == 401
    fresh = login(client, password="a brand new password").json()["token"]
    assert client.get("/api/me", headers=bearer(fresh)).status_code == 200


def test_reset_rejects_a_short_password_and_keeps_the_link(client):
    uid = register(client).json()["id"]
    digest = security.token_hash("still-good")
    later = (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds")
    storage.create_password_reset(uid, digest, later)
    assert reset(client, "still-good", "short").status_code == 400
    assert storage.find_password_reset(digest).used_at is None
    assert reset(client, "still-good", "long enough").status_code == 200


def test_a_failed_send_does_not_pretend_the_email_went_out(client, monkeypatch):
    smtp_ready(monkeypatch)
    register(client)

    def boom(to, link):
        raise OSError("smtp down")

    monkeypatch.setattr("api.mail.send_reset_email", boom)
    r = forgot(client)
    assert r.status_code == 503
    assert r.json()["error"] == "Could not send the reset email. Try again later."


def test_reset_requests_are_rate_limited(client, monkeypatch):
    smtp_ready(monkeypatch)
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: None)
    for _ in range(5):
        assert forgot(client, "nobody@example.com").status_code == 200
    assert forgot(client, "nobody@example.com").status_code == 429


def test_the_reset_limit_is_per_email_as_well_as_per_client(client, monkeypatch):
    smtp_ready(monkeypatch)
    monkeypatch.setattr("api.mail.send_reset_email", lambda to, link: None)
    auth.reset_limiter.reset()
    for _ in range(5):
        auth.reset_limiter.allow("email:" + EMAIL)
    assert forgot(client, EMAIL).status_code == 429
    assert forgot(client, "other@example.com").status_code == 200


def test_the_api_is_mounted_on_the_reflex_app():
    import StudyFlow.StudyFlow as page
    mounted = page.app.api_transformer
    assert mounted is not None
    c = TestClient(mounted)
    assert c.get("/api/health").json() == {"status": "ok"}
    assert c.get("/api/me").status_code == 401                      # answered by the API, not a 404
