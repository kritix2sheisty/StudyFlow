"""
tests/test_api_client.py
The web app's API client: real requests through the API's HTTP stack
in-process, a bearer token on every call, JSON in and out, and a
typed error for anything the API refuses.
"""

import asyncio
from datetime import date, timedelta

import pytest

import storage
from api import auth
from StudyFlow.api_client import ApiClient, ApiError


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    storage.set_db_path(tmp_path / "api_client.db")
    storage.init_db()
    auth.login_limiter.reset()
    auth.register_limiter.reset()
    yield


def run(coro):
    return asyncio.run(coro)


async def logged_in(email="ana@example.com") -> ApiClient:
    anon = ApiClient()
    await anon.register(email, "a long enough password")
    token = (await anon.login(email, "a long enough password"))["token"]
    return ApiClient(token)


def test_register_login_and_me_through_the_client():
    async def go():
        client = await logged_in()
        me = await client.me()
        return me
    me = run(go())
    assert me["email"] == "ana@example.com" and len(me["id"]) == 36


def test_errors_carry_the_apis_status_and_message():
    async def go():
        anon = ApiClient()
        await anon.register("ana@example.com", "a long enough password")
        try:
            await anon.login("ana@example.com", "wrong password")
        except ApiError as e:
            wrong = (e.status, e.message)
        try:
            await ApiClient("nonsense").me()
        except ApiError as e:
            unauth = (e.status, e.message)
        try:
            await anon.register("ana@example.com", "a long enough password")
        except ApiError as e:
            dup = e.status
        return wrong, unauth, dup
    wrong, unauth, dup = run(go())
    assert wrong == (401, auth.LOGIN_FAILED)
    assert unauth[0] == 401 and dup == 409


def test_assignments_slots_plan_and_focus_round_trip():
    async def go():
        client = await logged_in()
        due = (date.today() + timedelta(days=3)).isoformat()
        created = await client.create_assignment({"name": "Essay", "subject": "English", "due_date": due,
                                                  "estimated_hours": 2, "priority": "HIGH"})
        await client.add_slot({"weekday": date.today().strftime("%A").upper(), "start_hour": 16, "end_hour": 18})
        plan = await client.generate_plan()
        read = await client.plan()
        progress = await client.progress()
        updated = await client.update_assignment(created["id"], {**created, "estimated_hours": 3})
        stale = await client.plan()
        assert await client.delete_slot((await client.slots())[0]["id"]) is None
        await client.complete_assignment(created["id"])
        remaining = await client.assignments("active")
        current = await client.focus_current()
        return created, plan, read, progress, updated, stale, remaining, current
    created, plan, read, progress, updated, stale, remaining, current = run(go())
    assert created["name"] == "Essay" and isinstance(created["id"], int)
    assert plan["fresh"] is True and read["plan"] == plan
    assert progress["required_hours"] == 2.0 and progress["fresh"] is True
    assert updated["estimated_hours"] == 3.0
    assert stale == {"fresh": False, "plan": None}
    assert remaining == []
    assert current["active"] is False


def test_the_browser_address_is_forwarded_for_rate_limiting():
    """Ten failed logins from one browser do not lock out another browser using the same web app."""
    async def go():
        anon = ApiClient()
        await anon.register("ana@example.com", "a long enough password")
        first = ApiClient(browser_ip="10.0.0.1")
        second = ApiClient(browser_ip="10.0.0.2")
        for _ in range(10):
            try:
                await first.login("ana@example.com", "wrong password")
            except ApiError:
                pass
        try:
            await first.login("ana@example.com", "a long enough password")
            first_status = 200
        except ApiError as e:
            first_status = e.status
        auth.login_limiter.reset()                                  # the per-email limit is shared; clear it
        for _ in range(10):
            try:
                await first.login("ana@example.com", "wrong password")
            except ApiError:
                pass
        try:
            await second.login("ben@example.com", "irrelevant")
            second_status = 200
        except ApiError as e:
            second_status = e.status
        return first_status, second_status
    first_status, second_status = run(go())
    assert first_status == 429                                        # the first browser is limited
    assert second_status == 401                                       # the second browser is not (just a wrong login)
