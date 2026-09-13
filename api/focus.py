"""
api/focus.py
The Focus experience over HTTP: which study block is on now, which
comes next, and recording that a block was completed. The countdown
stays on the client; the server only knows the blocks and the clock.

    GET  /api/focus/current   -> {"active": bool, "session": {...}|null, "reason": ...}
    GET  /api/focus/next      -> {"session": {...}|null, "reason": ...}
    POST /api/focus/complete  -> {"recorded", "already_recorded", "session", "assignment"}

Sessions come from the student's stored plan (api/plan.py), and only
while it is fresh: a stale or missing plan answers with a reason
("plan_stale", "no_plan") instead of misleading blocks.

A completed session is its own record (storage.session_completions):
it never marks the assignment complete and never changes the plan's
inputs, so the plan stays fresh. Progress adds the hours done from
those records next to the engine's scheduled and remaining hours.
"""

import re
from datetime import date, datetime
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api.auth import ApiError, _json_body, current_user
from api.plan import plan_state

CLOCK = re.compile(r"^(\d{2}):(\d{2})$")


def _now() -> datetime:
    """The server's clock; tests replace this."""
    return datetime.now()


def _minutes(clock: str) -> Optional[int]:
    m = CLOCK.match(clock or "")
    if not m or int(m.group(1)) > 24 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def sessions_of(plan: dict) -> list[dict]:
    """Every work block in the plan as a session, in time order."""
    who = {a["name"]: a for a in plan.get("assignments", [])}
    out = []
    for day in plan.get("days", []):
        for b in day["blocks"]:
            if b["is_break"]:
                continue
            a = who.get(b["label"], {})
            start, end = _minutes(b["start"]), _minutes(b["end"])
            out.append({
                "assignment_id": a.get("id"), "assignment": b["label"], "subject": a.get("subject", ""),
                "date": day["date"], "start": b["start"], "end": b["end"],
                "start_minute": start, "end_minute": end, "duration_minutes": end - start,
            })
    return sorted(out, key=lambda s: (s["date"], s["start_minute"]))


def _public(s: dict, completed: bool, remaining: Optional[int] = None) -> dict:
    body = {k: s[k] for k in ("assignment_id", "assignment", "subject", "date", "start", "end", "duration_minutes")}
    body["completed"] = completed
    if remaining is not None:
        body["remaining_minutes"] = remaining
    return body


def _done_keys(user_id: str) -> set:
    return {(c.date, c.start_minute, c.end_minute) for c in storage.list_session_completions(user_id)}


def _is_done(s: dict, done: set) -> bool:
    return (s["date"], s["start_minute"], s["end_minute"]) in done


def _current(sessions: list[dict], now: datetime) -> Optional[dict]:
    today, minute = now.date().isoformat(), now.hour * 60 + now.minute
    return next((s for s in sessions if s["date"] == today and s["start_minute"] <= minute < s["end_minute"]), None)


def _next(sessions: list[dict], now: datetime, done: set) -> Optional[dict]:
    today, minute = now.date().isoformat(), now.hour * 60 + now.minute
    current = _current(sessions, now)
    floor = current["end_minute"] if current else minute
    return next((s for s in sessions
                 if not _is_done(s, done)
                 and (s["date"] > today or (s["date"] == today and s["start_minute"] >= floor and s is not current))),
                None)


def _sessions_for(user_id: str):
    """(reason, sessions): reason is None when the plan is fresh."""
    status, plan = plan_state(user_id)
    if status == "none":
        return "no_plan", []
    if status == "stale":
        return "plan_stale", []
    return None, sessions_of(plan)


# ---- Routes

async def current(request: Request) -> Response:
    user = current_user(request)
    reason, sessions = _sessions_for(user.id)
    if reason:
        return JSONResponse({"active": False, "session": None, "reason": reason})
    now = _now()
    s = _current(sessions, now)
    if s is None:
        return JSONResponse({"active": False, "session": None, "reason": "nothing_now"})
    remaining = max(0, s["end_minute"] - (now.hour * 60 + now.minute))
    return JSONResponse({"active": True, "session": _public(s, _is_done(s, _done_keys(user.id)), remaining), "reason": None})


async def next_session(request: Request) -> Response:
    user = current_user(request)
    reason, sessions = _sessions_for(user.id)
    if reason:
        return JSONResponse({"session": None, "reason": reason})
    s = _next(sessions, _now(), _done_keys(user.id))
    if s is None:
        return JSONResponse({"session": None, "reason": "nothing_next"})
    return JSONResponse({"session": _public(s, False), "reason": None})


def _requested_block(request_body: Optional[dict], sessions: list[dict], now: datetime) -> dict:
    """The block to complete: the one named in the body, or the current one."""
    if request_body is None:
        s = _current(sessions, now)
        if s is None:
            raise ApiError(404, "No study session is on right now.")
        return s
    day = request_body.get("date")
    try:
        date.fromisoformat(str(day))
    except (TypeError, ValueError):
        raise ApiError(400, "Give date as YYYY-MM-DD.")
    start, end = _minutes(str(request_body.get("start", ""))), _minutes(str(request_body.get("end", "")))
    if start is None or end is None:
        raise ApiError(400, "Give start and end as HH:MM.")
    s = next((x for x in sessions if x["date"] == day and x["start_minute"] == start and x["end_minute"] == end), None)
    if s is None:
        raise ApiError(404, "No such session in your plan.")
    return s


async def complete(request: Request) -> Response:
    user = current_user(request)
    status, plan = plan_state(user.id)
    if status == "none":
        raise ApiError(404, "No study session is on right now.")
    if status == "stale":
        raise ApiError(409, "Your plan needs to be regenerated before a session can be recorded.")
    body = await _json_body(request) if request.headers.get("content-length", "0") not in ("", "0") else None
    s = _requested_block(body, sessions_of(plan), _now())
    recorded = storage.add_session_completion(user.id, s["assignment_id"], s["date"], s["start_minute"], s["end_minute"])
    done = storage.done_minutes_by_assignment(user.id).get(s["assignment_id"], 0)
    required = next((a["required_hours"] for a in plan["assignments"] if a["id"] == s["assignment_id"]), 0.0)
    return JSONResponse({
        "recorded": True,
        "already_recorded": not recorded,
        "session": _public(s, True),
        "assignment": {"id": s["assignment_id"], "name": s["assignment"], "required_hours": required,
                       "done_hours": round(done / 60, 2), "done_percent": done_percent(done, required)},
    })


def done_percent(done_minutes: int, required_hours: float) -> int:
    if required_hours <= 0:
        return 0
    return min(100, round(100 * done_minutes / 60 / required_hours))
