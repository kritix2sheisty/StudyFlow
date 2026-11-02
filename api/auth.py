"""
api/auth.py
Register, login, logout and "who am I", plus the one dependency every
protected route uses: the current user, taken from the bearer token
and nothing else.

    POST /api/auth/register  {email, password}   -> 201 {id, email}
    POST /api/auth/login     {email, password}   -> 200 {token, expires_at}
    POST /api/auth/logout    bearer              -> 204
    GET  /api/me             bearer              -> 200 {id, email, created_at}
    POST /api/auth/forgot    {email}             -> 200 {ok: true}
    POST /api/auth/reset     {token, password}   -> 200 {ok: true}

Forgot always answers the same way whether or not the email is
registered, so the API does not reveal which emails have accounts.
The reset link is emailed only when SMTP is configured. A reset token
works once, expires in an hour, and logging in with the new password
ends every older session.

Login failure says the same thing for a wrong password and an unknown
email, so the API never reveals which emails are registered. Login and
register are rate limited per client address and per email. Events
are logged by user id, never by email or password.
"""

import logging
import os
import secrets
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import storage
from api import mail, security

log = logging.getLogger("studyflow.api")

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_FAILED = "Email or password is incorrect."

# The web app calls the API in-process over an ASGI transport whose
# client host is this fixed name; no network client can present it.
# Only then is X-Forwarded-For (the browser's address) trusted for
# rate limiting, so limits apply per student rather than to the web
# app as a whole.
WEB_CLIENT_HOST = "studyflow-web"

# A web app on another host cannot have that client host. It proves
# itself instead with STUDYFLOW_WEB_KEY in the X-StudyFlow-Web-Key header
# (the same value configured on both sides); only then is
# X-Forwarded-For trusted, so a hosted website still gets per-browser
# limits rather than one bucket for the whole school.
#
# Phones hitting a hosted API also share one proxy address. When
# STUDYFLOW_TRUST_PROXY is set (the API container), X-Forwarded-For is
# the phone's address and login limits apply per phone.
WEB_KEY_HEADER = "x-studyflow-web-key"


def _web_key() -> str:
    return os.environ.get("STUDYFLOW_WEB_KEY", "").strip()

login_limiter = security.RateLimiter(limit=10, window_seconds=15 * 60)
register_limiter = security.RateLimiter(limit=10, window_seconds=15 * 60)
reset_limiter = security.RateLimiter(limit=5, window_seconds=15 * 60)

RESET_MINUTES = 60
RESET_INVALID = "This reset link is invalid or has expired."


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


def _is_web_app(request: Request, host: str) -> bool:
    if host == WEB_CLIENT_HOST:
        return True
    key = _web_key()
    return bool(key) and secrets.compare_digest(request.headers.get(WEB_KEY_HEADER, ""), key)


def _trust_proxy() -> bool:
    """Container hosts put every phone behind one proxy address."""
    return os.environ.get("STUDYFLOW_TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}


def _client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    if _is_web_app(request, host):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        return f"web:{forwarded or 'unknown'}"
    if _trust_proxy():
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return host


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


async def forgot_password(request: Request) -> Response:
    """
    Email a one-time reset link. The answer is the same when the email
    is unknown, so a caller cannot learn who has an account. When SMTP
    is not configured, every caller gets the same 503.
    """
    if not mail.configured():
        raise ApiError(503, "Password reset email is not set up yet.")
    if not reset_limiter.allow(_client_key(request)):
        log.warning("reset rate limit hit")
        raise ApiError(429, "Too many attempts. Try again later.")
    body = await _json_body(request)
    email = str(body.get("email", "")).strip().lower()
    if not EMAIL.match(email):
        raise ApiError(400, "Enter a valid email address.")
    if not reset_limiter.allow(f"email:{email}"):
        log.warning("reset rate limit hit")
        raise ApiError(429, "Too many attempts. Try again later.")
    found = storage.get_user_by_email(email)
    if found is not None and found.password_hash:
        token = security.new_token()
        expires_at = (datetime.now() + timedelta(minutes=RESET_MINUTES)).isoformat(timespec="seconds")
        storage.create_password_reset(found.id, security.token_hash(token), expires_at)
        link = f"{mail.public_url()}/reset?token={quote(token)}"
        try:
            mail.send_reset_email(found.email, link)
        except Exception:
            log.exception("reset email failed user=%s", found.id)
            raise ApiError(503, "Could not send the reset email. Try again later.")
        log.info("reset email sent user=%s", found.id)
    return JSONResponse({"ok": True})


async def reset_password(request: Request) -> Response:
    """Set a new password from a reset link and log out every old session."""
    if not reset_limiter.allow(_client_key(request)):
        log.warning("reset rate limit hit")
        raise ApiError(429, "Too many attempts. Try again later.")
    body = await _json_body(request)
    token = str(body.get("token", "")).strip()
    password = body.get("password", "")
    if not isinstance(password, str) or len(password) < security.MIN_PASSWORD_LENGTH:
        raise ApiError(400, f"Use a password of at least {security.MIN_PASSWORD_LENGTH} characters.")
    user_id = storage.consume_password_reset(security.token_hash(token)) if token else None
    if user_id is None:
        raise ApiError(400, RESET_INVALID)
    storage.set_password(user_id, security.hash_password(password))
    storage.revoke_user_sessions(user_id)
    log.info("password reset user=%s", user_id)
    return JSONResponse({"ok": True})
