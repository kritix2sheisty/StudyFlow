"""
api/account.py
The one-time hand-over of the data StudyFlow kept before accounts
existed. Until PR #41 the app had a single built-in student; their
assignments, study time, plan and completed sessions are still there,
owned by DEFAULT_USER_ID, and nobody can log in as that student.

    GET  /api/account/local-data   -> is there anything to import, and how much
    POST /api/account/import-local -> give all of it to the caller

The import is explicit and once: after it the built-in student holds
nothing, so no later account can see or claim that data. It is a
feature of a single-machine installation; a shared deployment starts
with an empty built-in student and never offers it.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api.auth import current_user


async def local_data(request: Request) -> Response:
    current_user(request)
    summary = storage.local_data_summary()
    return JSONResponse({"available": any(summary.values()), **summary})


async def import_local(request: Request) -> Response:
    user = current_user(request)
    moved = storage.claim_local_data(user.id)
    return JSONResponse({"imported": any(moved.values()), **moved})
