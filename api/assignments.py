"""
api/assignments.py
A logged-in student's assignments over HTTP. Thin on purpose:

    request -> current_user() -> validate -> storage.* -> JSON

    GET    /api/assignments?status=active|completed|all   (default active)
    POST   /api/assignments                                 -> 201
    PUT    /api/assignments/{id}                            -> 200
    DELETE /api/assignments/{id}                            -> 204
    POST   /api/assignments/{id}/complete  {completed?}     -> 200

Every storage call carries the caller's user id, so another student's
assignment is simply not there: 404, never "forbidden", so the API
does not reveal what exists. No scheduling logic lives here.
"""

from datetime import date
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api.auth import ApiError, _json_body, current_user
from models import Assignment, Priority

STATUSES = ("active", "completed", "all")


# ---- Shapes

def to_json(a: Assignment) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "subject": a.subject,
        "due_date": a.due_date.isoformat(),
        "estimated_hours": a.estimated_hours,
        "priority": a.priority.name,
        "completed": a.completed,
    }


def _text(body: dict, field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"Give the assignment a {field}.")
    return value.strip()


def from_json(body: dict, completed_default: bool = False) -> Assignment:
    """Validate a JSON object into an Assignment (no id). Raises ApiError(400)."""
    name = _text(body, "name")
    subject = _text(body, "subject")
    try:
        due = date.fromisoformat(str(body.get("due_date", "")))
    except ValueError:
        raise ApiError(400, "Give due_date as YYYY-MM-DD.")
    hours = body.get("estimated_hours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours < 0:
        raise ApiError(400, "Give estimated_hours as a number of hours, 0 or more.")
    priority_name = body.get("priority", "MEDIUM")
    if priority_name not in Priority.__members__:
        raise ApiError(400, "Priority must be LOW, MEDIUM or HIGH.")
    completed = body.get("completed", completed_default)
    if not isinstance(completed, bool):
        raise ApiError(400, "completed must be true or false.")
    return Assignment(name=name, subject=subject, due_date=due, estimated_hours=float(hours),
                      priority=Priority[priority_name], completed=completed)


def _assignment_id(request: Request) -> int:
    try:
        return int(request.path_params["assignment_id"])
    except (KeyError, ValueError):
        raise ApiError(404, "No such assignment.")


def _own(user_id: str, assignment_id: int) -> Assignment:
    """The caller's assignment with this id, or 404."""
    found = next((a for a in storage.list_assignments(user_id) if a.id == assignment_id), None)
    if found is None:
        raise ApiError(404, "No such assignment.")
    return found


# ---- Routes

async def list_assignments(request: Request) -> Response:
    user = current_user(request)
    status = request.query_params.get("status", "active")
    if status not in STATUSES:
        raise ApiError(400, "status must be active, completed or all.")
    rows = storage.list_assignments(user.id, include_completed=(status != "active"))
    if status == "completed":
        rows = [a for a in rows if a.completed]
    return JSONResponse([to_json(a) for a in rows])


async def create_assignment(request: Request) -> Response:
    user = current_user(request)
    assignment = from_json(await _json_body(request))
    assignment.id = storage.add_assignment(user.id, assignment)
    return JSONResponse(to_json(assignment), status_code=201)


async def update_assignment(request: Request) -> Response:
    user = current_user(request)
    existing = _own(user.id, _assignment_id(request))
    assignment = from_json(await _json_body(request), completed_default=existing.completed)
    assignment.id = existing.id
    if not storage.update_assignment(user.id, assignment):
        raise ApiError(404, "No such assignment.")
    return JSONResponse(to_json(assignment))


async def delete_assignment(request: Request) -> Response:
    user = current_user(request)
    if not storage.delete_assignment(user.id, _assignment_id(request)):
        raise ApiError(404, "No such assignment.")
    return Response(status_code=204)


async def complete_assignment(request: Request) -> Response:
    user = current_user(request)
    existing = _own(user.id, _assignment_id(request))
    completed = True
    if request.headers.get("content-length", "0") not in ("", "0"):
        body = await _json_body(request)
        completed = body.get("completed", True)
        if not isinstance(completed, bool):
            raise ApiError(400, "completed must be true or false.")
    if not storage.mark_assignment_complete(user.id, existing.id, completed):
        raise ApiError(404, "No such assignment.")
    existing.completed = completed
    return JSONResponse(to_json(existing))
