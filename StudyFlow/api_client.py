"""
StudyFlow/api_client.py
The web app's only way to the student's data: the StudyFlow HTTP API,
called exactly as any other client would, with a bearer token and
JSON. Nothing in the Reflex app imports storage or the engine any
more; ownership, validation and scheduling all happen behind the API.

Transport. By default requests go through the API's own HTTP stack
in-process (httpx's ASGI transport over the same Starlette app the
backend mounts): real requests, real routing, real authentication and
status codes, no socket and no port to configure, and no risk of a
handler blocking the server it is calling. Set STUDYFLOW_API_URL to
point the web app at an API running elsewhere instead.

Because the web app shares one process with the API, it tells the
API which browser it is acting for (X-Forwarded-For) so login and
registration rate limits apply per student, not to the web app as a
whole. The API trusts that header only on this in-process transport,
whose client host is fixed to WEB_CLIENT_HOST and cannot be reached
from the network, or when the web app proves itself over the network
with STUDYFLOW_WEB_KEY (sent as X-StudyFlow-Web-Key; the same value
must be set on the API host).
"""

import os
from typing import Any, Optional

import httpx

from api import create_api
from api.auth import WEB_CLIENT_HOST

_app = None


class ApiError(Exception):
    """A non-2xx answer from the API, with its status and message."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _api_app():
    global _app
    if _app is None:
        _app = create_api()
    return _app


def _make_client() -> httpx.AsyncClient:
    url = os.environ.get("STUDYFLOW_API_URL", "").strip()
    if url:
        return httpx.AsyncClient(base_url=url, timeout=20)
    # A failure inside the API becomes a 500 answer (and an ApiError here),
    # exactly as it would over the network, instead of a raised exception.
    transport = httpx.ASGITransport(app=_api_app(), client=(WEB_CLIENT_HOST, 0), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://studyflow.api", timeout=20)


class ApiClient:
    """One student's view of the API, given their session token."""

    def __init__(self, token: str = "", browser_ip: str = ""):
        self.token = token
        self.browser_ip = browser_ip

    # ---- Plumbing

    async def _request(self, method: str, path: str, json: Any = None, params: Optional[dict] = None) -> Any:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.browser_ip:
            headers["X-Forwarded-For"] = self.browser_ip
        web_key = os.environ.get("STUDYFLOW_WEB_KEY", "").strip()
        if web_key:                                                       # a hosted web app proves itself to a hosted API
            headers["X-StudyFlow-Web-Key"] = web_key
        async with _make_client() as client:
            response = await client.request(method, path, json=json, params=params, headers=headers)
        if response.status_code == 204:
            return None
        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text or "The API gave no answer."}
        if response.status_code >= 400:
            raise ApiError(response.status_code, body.get("error", "Something went wrong.") if isinstance(body, dict) else str(body))
        return body

    # ---- Account

    async def register(self, email: str, password: str) -> dict:
        return await self._request("POST", "/api/auth/register", json={"email": email, "password": password})

    async def login(self, email: str, password: str) -> dict:
        return await self._request("POST", "/api/auth/login", json={"email": email, "password": password})

    async def logout(self) -> None:
        await self._request("POST", "/api/auth/logout")

    async def me(self) -> dict:
        return await self._request("GET", "/api/me")

    async def local_data(self) -> dict:
        return await self._request("GET", "/api/account/local-data")

    async def import_local_data(self) -> dict:
        return await self._request("POST", "/api/account/import-local")

    # ---- Assignments

    async def assignments(self, status: str = "all") -> list:
        return await self._request("GET", "/api/assignments", params={"status": status})

    async def create_assignment(self, payload: dict) -> dict:
        return await self._request("POST", "/api/assignments", json=payload)

    async def update_assignment(self, assignment_id: int, payload: dict) -> dict:
        return await self._request("PUT", f"/api/assignments/{assignment_id}", json=payload)

    async def delete_assignment(self, assignment_id: int) -> None:
        await self._request("DELETE", f"/api/assignments/{assignment_id}")

    async def complete_assignment(self, assignment_id: int, completed: bool = True) -> dict:
        return await self._request("POST", f"/api/assignments/{assignment_id}/complete", json={"completed": completed})

    # ---- Study time

    async def slots(self) -> list:
        return await self._request("GET", "/api/study-time")

    async def add_slot(self, payload: dict) -> dict:
        return await self._request("POST", "/api/study-time", json=payload)

    async def delete_slot(self, slot_id: int) -> None:
        await self._request("DELETE", f"/api/study-time/{slot_id}")

    # ---- Plan, progress, focus

    async def generate_plan(self) -> dict:
        return await self._request("POST", "/api/plan/generate")

    async def plan(self) -> dict:
        return await self._request("GET", "/api/plan")

    async def progress(self) -> dict:
        return await self._request("GET", "/api/plan/progress")

    async def focus_current(self) -> dict:
        return await self._request("GET", "/api/focus/current")

    async def focus_next(self) -> dict:
        return await self._request("GET", "/api/focus/next")

    async def focus_complete(self, block: Optional[dict] = None) -> dict:
        return await self._request("POST", "/api/focus/complete", json=block)
