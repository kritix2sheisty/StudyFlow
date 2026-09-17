"""
tests/test_web_key.py
When the web app talks to the API over the network (a hosted website
calling a hosted API), every student's login arrives from the web
server's address. So the API must know which browser it is acting for,
or ten wrong passwords from one student would lock out the school.

The in-process transport proves itself by its fixed client host. Over
the network, the web app proves itself with a shared key in the
X-StudyFlow-Web-Key header (STUDYFLOW_WEB_KEY on both sides); only then
is X-Forwarded-For trusted for rate limiting.
"""

import httpx
import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

import storage
from api import auth
from api.main import create_api
from StudyFlow import api_client
from StudyFlow.api_client import ApiClient, ApiError


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    storage.set_db_path(tmp_path / "web_key.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    monkeypatch.delenv("STUDYFLOW_WEB_KEY", raising=False)
    yield


def request_from(host: str, headers: dict) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "query_string": b"",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
             "client": (host, 12345)}
    return Request(scope)


def test_a_network_caller_without_the_key_is_limited_as_itself(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_WEB_KEY", "shared-secret")
    key = auth._client_key(request_from("203.0.113.9", {"X-Forwarded-For": "10.0.0.1"}))
    assert key == "203.0.113.9"                                          # the forwarded address is ignored


def test_a_network_caller_with_the_right_key_is_limited_per_browser(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_WEB_KEY", "shared-secret")
    key = auth._client_key(request_from("203.0.113.9", {"X-Forwarded-For": "10.0.0.1", "X-StudyFlow-Web-Key": "shared-secret"}))
    assert key == "web:10.0.0.1"


def test_a_wrong_or_empty_key_never_unlocks_forwarding(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_WEB_KEY", "shared-secret")
    assert auth._client_key(request_from("203.0.113.9", {"X-Forwarded-For": "10.0.0.1", "X-StudyFlow-Web-Key": "wrong"})) == "203.0.113.9"
    monkeypatch.setenv("STUDYFLOW_WEB_KEY", "")
    assert auth._client_key(request_from("203.0.113.9", {"X-Forwarded-For": "10.0.0.1", "X-StudyFlow-Web-Key": ""})) == "203.0.113.9"
    monkeypatch.delenv("STUDYFLOW_WEB_KEY")
    assert auth._client_key(request_from("203.0.113.9", {"X-Forwarded-For": "10.0.0.1", "X-StudyFlow-Web-Key": "anything"})) == "203.0.113.9"


def test_the_in_process_transport_still_needs_no_key():
    assert auth._client_key(request_from(auth.WEB_CLIENT_HOST, {"X-Forwarded-For": "10.0.0.7"})) == "web:10.0.0.7"


def test_over_http_ten_wrong_passwords_from_one_browser_do_not_lock_out_another(monkeypatch):
    """The whole path: a network client with the key, two browsers, one abusive."""
    monkeypatch.setenv("STUDYFLOW_WEB_KEY", "shared-secret")
    client = TestClient(create_api())                                    # client host "testclient": not the in-process host
    client.post("/api/auth/register", json={"email": "ana@example.com", "password": "a long enough password"})
    auth.login_limiter.reset()
    abusive = {"X-Forwarded-For": "10.0.0.1", "X-StudyFlow-Web-Key": "shared-secret"}
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "ana@example.com", "password": "wrong"}, headers=abusive)
    assert client.post("/api/auth/login", json={"email": "ana@example.com", "password": "a long enough password"}, headers=abusive).status_code == 429
    auth.login_limiter.reset()
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "ana@example.com", "password": "wrong"}, headers=abusive)
    other = {"X-Forwarded-For": "10.0.0.2", "X-StudyFlow-Web-Key": "shared-secret"}
    assert client.post("/api/auth/login", json={"email": "ben@example.com", "password": "irrelevant"}, headers=other).status_code == 401


def test_the_web_app_sends_the_key_when_it_talks_over_the_network(monkeypatch):
    """ApiClient adds X-StudyFlow-Web-Key from STUDYFLOW_WEB_KEY, so a hosted web app is trusted per browser."""
    monkeypatch.setenv("STUDYFLOW_WEB_KEY", "shared-secret")
    seen = {}

    async def capture(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        return httpx.Response(401, json={"error": auth.LOGIN_FAILED})

    monkeypatch.setattr(api_client, "_make_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(capture), base_url="https://api.example"))
    import asyncio
    with pytest.raises(ApiError):
        asyncio.run(ApiClient(browser_ip="10.0.0.1").login("ana@example.com", "wrong"))
    assert seen["headers"]["x-forwarded-for"] == "10.0.0.1"
    assert seen["headers"]["x-studyflow-web-key"] == "shared-secret"


def test_the_web_app_sends_no_key_header_when_none_is_configured(monkeypatch):
    seen = {}

    async def capture(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(api_client, "_make_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(capture), base_url="https://api.example"))
    import asyncio
    asyncio.run(ApiClient()._request("GET", "/api/health"))
    assert "x-studyflow-web-key" not in seen["headers"]
