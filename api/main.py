"""
api/main.py
The StudyFlow API as a Starlette app, mounted on the Reflex backend
with rx.App(api_transformer=create_api()): requests under /api are
answered here, everything else falls through to Reflex.

Starlette is what Reflex's own backend runs on, so this adds no
framework. Every route returns JSON; every ApiError becomes
{"error": message} with its status code.
"""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from api import assignments, auth
from api.auth import ApiError


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": "Not found."}, status_code=404)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_api() -> Starlette:
    routes = [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/auth/register", auth.register, methods=["POST"]),
        Route("/api/auth/login", auth.login, methods=["POST"]),
        Route("/api/auth/logout", auth.logout, methods=["POST"]),
        Route("/api/me", auth.me, methods=["GET"]),
        Route("/api/assignments", assignments.list_assignments, methods=["GET"]),
        Route("/api/assignments", assignments.create_assignment, methods=["POST"]),
        Route("/api/assignments/{assignment_id}", assignments.update_assignment, methods=["PUT"]),
        Route("/api/assignments/{assignment_id}", assignments.delete_assignment, methods=["DELETE"]),
        Route("/api/assignments/{assignment_id}/complete", assignments.complete_assignment, methods=["POST"]),
    ]
    return Starlette(routes=routes, exception_handlers={ApiError: _api_error})
