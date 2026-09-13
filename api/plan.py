"""
api/plan.py
The scheduling engine over HTTP, for the authenticated student only.

    POST /api/plan/generate   -> 200 the plan (400 with a message when
                                 there is nothing to plan)
    GET  /api/plan            -> 200 {"fresh": bool, "plan": {...} | null}
    GET  /api/plan/progress   -> 200 totals, statuses, risks, completed work

The engine runs here and nowhere else: generate calls
study_plan.generate_study_plan() on the student's own assignments and
study time, turns the result into JSON with the same helpers the web
app uses (plan_view), and stores that JSON with the fingerprint of
the inputs it came from. A stored plan is served only while the
student's data still matches that fingerprint, the same freshness
rule the web app applies on every page load. Nothing here schedules,
prioritises, or rates risk.
"""

import json
from datetime import date, datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api.auth import ApiError, current_user
from schedule_builder import BREAK_LABEL
from study_plan import StudyPlan, generate_study_plan
from StudyFlow import plan_view


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def plan_to_json(plan: StudyPlan, slots, today: date, generated_at: str) -> dict:
    """The engine's StudyPlan as the API's plan object. Field names follow plan_view."""
    days = [
        {
            "date": day.isoformat(),
            "label": day.strftime("%A %d %b"),
            "blocks": [
                {"start": _clock(b.start_minute), "end": _clock(b.end_minute), "time": b.format_time_range(),
                 "label": b.label, "is_break": b.label == BREAK_LABEL}
                for b in blocks
            ],
        }
        for day, blocks in sorted(plan.schedule.by_date.items())
    ]
    assignments = [
        {"id": int(r.id), "name": r.name, "subject": r.subject, "due_date": r.due, "status": r.status,
         "required_hours": float(r.required), "scheduled_hours": float(r.scheduled),
         "remaining_hours": float(r.remaining), "percent": r.percent, "risk": r.risk}
        for r in plan_view.status_rows(plan, slots, today)
    ]
    return {
        "fresh": True,
        "generated_at": generated_at,
        "required_hours": plan.required_hours,
        "scheduled_hours": plan.scheduled_hours,
        "unscheduled_hours": plan.unscheduled_hours,
        "completion_percentage": round(plan.completion, 1),
        "days": days,
        "assignments": assignments,
    }


def _inputs(user_id: str):
    return storage.list_assignments(user_id, include_completed=False), storage.list_time_slots(user_id)


def plan_state(user_id: str) -> tuple[str, dict | None]:
    """
    ("none", None) before any plan exists, ("stale", None) when the
    student's data no longer matches what the stored plan was built
    from, ("fresh", plan) otherwise. One freshness rule, shared with
    the web app: plan_view.plan_input_fingerprint().
    """
    stored = storage.get_plan(user_id)
    if stored is None:
        return "none", None
    assignments, slots = _inputs(user_id)
    if plan_view.plan_input_fingerprint(assignments, slots) != stored.fingerprint:
        return "stale", None
    return "fresh", json.loads(stored.plan_json)


def _fresh_plan(user_id: str) -> dict | None:
    """The stored plan if the student's data still matches what it was built from."""
    return plan_state(user_id)[1]


# ---- Routes

async def generate(request: Request) -> Response:
    user = current_user(request)
    assignments, slots = _inputs(user.id)
    message = plan_view.guard_message(assignments, slots)
    if message:
        raise ApiError(400, message)
    today = date.today()
    plan = generate_study_plan(assignments, slots, today=today)
    payload = plan_to_json(plan, slots, today, datetime.now().isoformat(timespec="seconds"))
    storage.save_plan(user.id, plan_view.plan_input_fingerprint(assignments, slots),
                      payload["generated_at"], json.dumps(payload))
    return JSONResponse(payload)


async def get_plan(request: Request) -> Response:
    user = current_user(request)
    plan = _fresh_plan(user.id)
    return JSONResponse({"fresh": plan is not None, "plan": plan})


async def progress(request: Request) -> Response:
    user = current_user(request)
    everything = storage.list_assignments(user.id, include_completed=True)
    active = [a for a in everything if not a.completed]
    completed = [a.name for a in everything if a.completed]
    plan = _fresh_plan(user.id)
    if plan is None:
        body = {"fresh": False, "required_hours": round(sum(a.estimated_hours for a in active), 1),
                "scheduled_hours": 0.0, "unscheduled_hours": 0.0, "completion_percentage": 0.0, "assignments": []}
    else:
        body = {key: plan[key] for key in ("fresh", "required_hours", "scheduled_hours",
                                          "unscheduled_hours", "completion_percentage", "assignments")}
    # Hours done come from completed focus sessions (api/focus.py); they sit
    # next to the engine's scheduled and remaining hours, never inside them.
    done = storage.done_minutes_by_assignment(user.id)
    body["assignments"] = [
        {**a, "done_hours": round(done.get(a["id"], 0) / 60, 2),
         "done_percent": _done_percent(done.get(a["id"], 0), a["required_hours"])}
        for a in body["assignments"]
    ]
    body.update({
        "completed": completed, "active_count": len(active), "completed_count": len(completed),
        "done_hours": round(sum(done.values()) / 60, 2),
        "sessions_completed": len(storage.list_session_completions(user.id)),
    })
    return JSONResponse(body)


def _done_percent(done_minutes: int, required_hours: float) -> int:
    if required_hours <= 0:
        return 0
    return min(100, round(100 * done_minutes / 60 / required_hours))
