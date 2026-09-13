"""
api/study_time.py
A logged-in student's weekly study slots over HTTP. Thin on purpose:

    request -> current_user() -> validate -> storage.* -> JSON

    GET    /api/study-time           -> 200 list, in weekday order
    POST   /api/study-time           -> 201 the stored slot
    DELETE /api/study-time/{id}      -> 204

A slot is {weekday: "MONDAY".."SUNDAY", start_hour, end_hour} on the
24-hour clock, whole hours, end after start, as models.TimeSlot has
always been. Another student's slot, or an unknown id, is a 404.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api.auth import ApiError, _json_body, current_user
from models import TimeSlot, Weekday


def to_json(t: TimeSlot) -> dict:
    return {
        "id": t.id,
        "weekday": t.weekday.name,
        "start_hour": t.start_hour,
        "end_hour": t.end_hour,
        "hours": t.duration_hours,
    }


def _hour(body: dict, field: str, low: int, high: int) -> int:
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise ApiError(400, f"{field} must be a whole hour from {low} to {high}.")
    return value


def from_json(body: dict) -> TimeSlot:
    """Validate a JSON object into a TimeSlot (no id). Raises ApiError(400)."""
    weekday = body.get("weekday")
    if not isinstance(weekday, str) or weekday.strip().upper() not in Weekday.__members__:
        raise ApiError(400, "weekday must be one of MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY.")
    start = _hour(body, "start_hour", 0, 23)
    end = _hour(body, "end_hour", 1, 24)
    if end <= start:
        raise ApiError(400, "end_hour must be after start_hour.")
    return TimeSlot(weekday=Weekday[weekday.strip().upper()], start_hour=start, end_hour=end)


def _slot_id(request: Request) -> int:
    try:
        return int(request.path_params["slot_id"])
    except (KeyError, ValueError):
        raise ApiError(404, "No such study slot.")


# ---- Routes

async def list_slots(request: Request) -> Response:
    user = current_user(request)
    return JSONResponse([to_json(t) for t in storage.list_time_slots(user.id)])


async def create_slot(request: Request) -> Response:
    user = current_user(request)
    slot = from_json(await _json_body(request))
    slot.id = storage.add_time_slot(user.id, slot)
    return JSONResponse(to_json(slot), status_code=201)


async def delete_slot(request: Request) -> Response:
    user = current_user(request)
    if not storage.delete_time_slot(user.id, _slot_id(request)):
        raise ApiError(404, "No such study slot.")
    return Response(status_code=204)
