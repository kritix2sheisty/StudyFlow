"""
api/auth.py
Register, login, logout and "who am I", plus the one dependency every
protected route uses: the current user, taken from the bearer token
and nothing else.

    POST /api/auth/register  {email, password}   -> 201 {id, email}
    POST /api/auth/login     {email, password}   -> 200 {token, expires_at}
    POST /api/auth/logout    bearer              -> 204
    GET  /api/me             bearer              -> 200 {id, email, created_at}

Login failure says the same thing for a wrong password and an unknown
email, so the API never reveals which emails are registered. Login and
register are rate limited per client address and per email. Events
are logged by user id, never by email or password.
"""

import logging
import re
from datetime import datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api import security

log = logging.getLogger("studyflow.api")

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_FAILED = "Email or password is incorrect."

login_limiter = security.RateLimiter(limit=10, window_seconds=15 * 60)
register_limiter = security.RateLimiter(limit=10, window_seconds=15 * 60)


class ApiError(Exception):
    """An error the API reports to the client as JSON with a status code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---- Helpers

async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise ApiError(400, "Send a JSON body.")
    if not isinstance(body, dict):
        raise ApiError(400, "Send a JSON object.")
    return body


def _credentials(body: dict) -> tuple[str, str]:
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    if not EMAIL.match(email):
        raise ApiError(400, "Enter a valid email address.")
    if not isinstance(password, str) or len(password) < security.MIN_PASSWORD_LENGTH:
        raise ApiError(400, f"Use a password of at least {security.MIN_PASSWORD_LENGTH} characters.")
    return email, password


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "Sign in to continue.")
    return token.strip()


def current_user(request: Request) -> storage.User:
    """
    The student behind the bearer token: the session must exist, be
    unrevoked and unexpired. A valid call extends the session's
    inactivity expiry. Raises ApiError(401) otherwise.
    """
    token = _bearer(request)
    digest = security.token_hash(token)
    session = storage.find_session(digest)
    if session is None or session.revoked_at is not None:
        raise ApiError(401, "Sign in to continue.")
    if datetime.fromisoformat(session.expires_at) <= datetime.now():
        raise ApiError(401, "Your session has expired. Sign in again.")
    user = storage.get_user(session.user_id)
    if user is None:
        raise ApiError(401, "Sign in to continue.")
    storage.touch_session(digest, security.session_expiry())
    return user


# ---- Routes

async def register(request: Request) -> Response:
    if not register_limiter.allow(_client_key(request)):
        log.warning("register rate limit hit for client")
        raise ApiError(429, "Too many attempts. Try again later.")
    email, password = _credentials(await _json_body(request))
    if storage.get_user_by_email(email) is not None:
        raise ApiError(409, "That email is already registered.")
    user_id = storage.add_user(email)
    storage.set_password(user_id, security.hash_password(password))
    log.info("register user=%s", user_id)
    return JSONResponse({"id": user_id, "email": email}, status_code=201)


async def login(request: Request) -> Response:
    body = await _json_body(request)
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    if not login_limiter.allow(_client_key(request)) or not login_limiter.allow(f"email:{email}"):
        log.warning("login rate limit hit")
        raise ApiError(429, "Too many attempts. Try again later.")
    found = storage.get_user_by_email(email)
    if found is None or not found.password_hash or not isinstance(password, str) \
            or not security.verify_password(password, found.password_hash):
        log.info("login failed user=%s", found.id if found else "unknown")
        raise ApiError(401, LOGIN_FAILED)
    token = security.new_token()
    expires_at = security.session_expiry()
    storage.create_session(found.id, security.token_hash(token), expires_at)
    log.info("login ok user=%s", found.id)
    return JSONResponse({"token": token, "expires_at": expires_at})


async def logout(request: Request) -> Response:
    token = _bearer(request)
    storage.revoke_session(security.token_hash(token))       # revoking an unknown token is harmless
    return Response(status_code=204)


async def me(request: Request) -> Response:
    user = current_user(request)
    return JSONResponse({"id": user.id, "email": user.email, "created_at": user.created_at})
