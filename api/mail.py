"""
api/mail.py
The one outbound email StudyFlow sends: a password-reset link.

Nothing is sent until the host has an SMTP account. That is three
settings: STUDYFLOW_SMTP_HOST, STUDYFLOW_SMTP_FROM, and
STUDYFLOW_PUBLIC_URL (the link in the message). STUDYFLOW_SMTP_PORT
defaults to 587 (STARTTLS); port 465 uses SSL. STUDYFLOW_SMTP_USER
and STUDYFLOW_SMTP_PASSWORD are the mailbox login, when the server
requires one.
"""

import os
import smtplib
from email.message import EmailMessage

RESET_SUBJECT = "Reset your StudyFlow password"


def _setting(name: str) -> str:
    return os.environ.get(name, "").strip()


def configured() -> bool:
    """True when a reset link can actually be emailed."""
    return bool(_setting("STUDYFLOW_SMTP_HOST") and _setting("STUDYFLOW_SMTP_FROM")
                and _setting("STUDYFLOW_PUBLIC_URL"))


def public_url() -> str:
    return _setting("STUDYFLOW_PUBLIC_URL").rstrip("/")


def send_reset_email(to: str, link: str) -> None:
    """Email `link` to `to`. Raises if SMTP is not configured or the send fails."""
    if not configured():
        raise RuntimeError("password reset email is not configured")
    message = EmailMessage()
    message["Subject"] = RESET_SUBJECT
    message["From"] = _setting("STUDYFLOW_SMTP_FROM")
    message["To"] = to
    message.set_content(
        "You asked to reset your StudyFlow password.\n\n"
        "Open this link to choose a new one. It expires in one hour and works once.\n\n"
        f"{link}\n\n"
        "If you did not ask for this, you can ignore this email.\n"
    )
    host = _setting("STUDYFLOW_SMTP_HOST")
    port = int(os.environ.get("STUDYFLOW_SMTP_PORT", "587") or "587")
    user = _setting("STUDYFLOW_SMTP_USER")
    password = os.environ.get("STUDYFLOW_SMTP_PASSWORD", "")
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        smtp = smtplib.SMTP(host, port, timeout=20)
        smtp.starttls()
    try:
        if user:
            smtp.login(user, password)
        smtp.send_message(message)
    finally:
        smtp.quit()
