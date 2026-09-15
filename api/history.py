"""
api/history.py
Session history over HTTP: the study blocks a student recorded, and the
few numbers the phone's History and Progress screens need, computed
once here rather than on every phone.

    GET /api/focus/history?days=7  -> {
        "days", "from", "to",
        "sessions": [ {id, assignment_id, assignment, subject, date, start, end, minutes, completed_at}, ... ],
        "minutes", "sessions_count",
        "by_day":     [ {date, minutes, sessions}, ... ]   one entry per day in the window, oldest first
        "by_subject": [ {subject, minutes, sessions}, ... ] largest first
        "streak_days",
        "today": {minutes, sessions, planned_minutes, planned_sessions}
    }

Rules:
- The window is the last `days` days including today (1 to 90, default 7).
  Sessions come newest first.
- A session belongs to history even if its assignment was deleted since;
  it reads "Removed assignment" with no subject. The minutes were studied.
- The streak is consecutive days with at least one recorded session,
  counted back from today, or from yesterday when today has none yet,
  so a streak stays alive until the day is over.
- Today's planned minutes come from the plan only while it is fresh
  (api/plan.py); a stale or missing plan plans nothing.
Nothing here touches the engine, the plan or the assignments.
"""

from collections import defaultdict
from datetime import date, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api.auth import ApiError, current_user
from api.focus import sessions_of
from api.plan import plan_state

DEFAULT_DAYS = 7
MAX_DAYS = 90
REMOVED = "Removed assignment"


def _today() -> date:
    """The server's date; tests replace this."""
    return date.today()


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _days_param(request: Request) -> int:
    raw = request.query_params.get("days")
    if raw is None:
        return DEFAULT_DAYS
    try:
        days = int(raw)
    except ValueError:
        days = 0
    if not 1 <= days <= MAX_DAYS:
        raise ApiError(400, f"Give days as a whole number from 1 to {MAX_DAYS}.")
    return days


def streak_days(dates_with_sessions: set, today: date) -> int:
    """Consecutive days with a session, ending today or, if today is empty so far, yesterday."""
    cursor = today if today.isoformat() in dates_with_sessions else today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in dates_with_sessions:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _todays_plan(user_id: str, today: date) -> tuple[int, int]:
    """(planned minutes, planned sessions) for today from a fresh plan, else zeros."""
    status, plan = plan_state(user_id)
    if status != "fresh":
        return 0, 0
    todays = [s for s in sessions_of(plan) if s["date"] == today.isoformat()]
    return sum(s["duration_minutes"] for s in todays), len(todays)


async def history(request: Request) -> Response:
    user = current_user(request)
    days = _days_param(request)
    today = _today()
    start = today - timedelta(days=days - 1)

    names = {a.id: a for a in storage.list_assignments(user.id, include_completed=True)}
    all_completions = storage.list_session_completions(user.id)
    dates_with_sessions = {c.date for c in all_completions}

    in_window = [c for c in all_completions if start.isoformat() <= c.date <= today.isoformat()]
    sessions = []
    for c in sorted(in_window, key=lambda c: (c.date, c.start_minute), reverse=True):
        a = names.get(c.assignment_id)
        sessions.append({
            "id": c.id, "assignment_id": c.assignment_id,
            "assignment": a.name if a else REMOVED, "subject": a.subject if a else "",
            "date": c.date, "start": _clock(c.start_minute), "end": _clock(c.end_minute),
            "minutes": c.end_minute - c.start_minute, "completed_at": c.completed_at,
        })

    per_day = defaultdict(lambda: [0, 0])
    per_subject = defaultdict(lambda: [0, 0])
    for s in sessions:
        per_day[s["date"]][0] += s["minutes"]; per_day[s["date"]][1] += 1
        per_subject[s["subject"]][0] += s["minutes"]; per_subject[s["subject"]][1] += 1

    by_day = []
    for n in range(days):
        d = (start + timedelta(days=n)).isoformat()
        minutes, count = per_day[d]
        by_day.append({"date": d, "minutes": minutes, "sessions": count})
    by_subject = sorted(
        ({"subject": subject, "minutes": m, "sessions": n} for subject, (m, n) in per_subject.items()),
        key=lambda x: (-x["minutes"], x["subject"]),
    )

    today_minutes, today_count = per_day[today.isoformat()]
    planned_minutes, planned_sessions = _todays_plan(user.id, today)

    return JSONResponse({
        "days": days, "from": start.isoformat(), "to": today.isoformat(),
        "sessions": sessions,
        "minutes": sum(s["minutes"] for s in sessions), "sessions_count": len(sessions),
        "by_day": by_day, "by_subject": by_subject,
        "streak_days": streak_days(dates_with_sessions, today),
        "today": {"minutes": today_minutes, "sessions": today_count,
                  "planned_minutes": planned_minutes, "planned_sessions": planned_sessions},
    })
