"""
api
StudyFlow's HTTP API: the boundary between clients (the Reflex web
app, a future mobile app) and the student's data and the scheduling
engine.

    api/security.py   password hashing, session tokens, rate limiting
    api/auth.py       register, login, logout, me
    api/main.py       the Starlette app, mounted on the Reflex backend

Rules that every route follows:
  - The current user comes from the bearer token, never from the
    request body or query.
  - Storage is called with that user's id (PR #41), so a route can
    only ever touch the caller's own rows.
  - The API translates; it never re-implements the scheduling engine.
"""

from api.main import create_api

__all__ = ["create_api"]
