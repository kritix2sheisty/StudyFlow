"""
tests/test_mail.py
The password-reset email: it stays quiet until SMTP is configured,
and the message it builds carries the one-hour link.
"""

import smtplib

import pytest

from api import mail


def test_mail_is_not_configured_by_default(monkeypatch):
    for name in ("STUDYFLOW_SMTP_HOST", "STUDYFLOW_SMTP_FROM", "STUDYFLOW_PUBLIC_URL"):
        monkeypatch.delenv(name, raising=False)
    assert mail.configured() is False
    with pytest.raises(RuntimeError):
        mail.send_reset_email("ana@example.com", "https://studyflow.example/reset?token=abc")


def test_send_reset_email_message_contents(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STUDYFLOW_SMTP_FROM", "StudyFlow <noreply@example.com>")
    monkeypatch.setenv("STUDYFLOW_SMTP_USER", "mailbox")
    monkeypatch.setenv("STUDYFLOW_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("STUDYFLOW_PUBLIC_URL", "https://studyflow.example/")
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["endpoint"] = (host, port)
            captured["client"] = self

        def starttls(self):
            captured["starttls"] = True

        def login(self, user, password):
            captured["login"] = (user, password)

        def send_message(self, message):
            captured["message"] = message

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    link = "https://studyflow.example/reset?token=abc"
    mail.send_reset_email("ana@example.com", link)
    message = captured["message"]
    assert message["Subject"] == "Reset your StudyFlow password"
    assert message["From"] == "StudyFlow <noreply@example.com>"
    assert message["To"] == "ana@example.com"
    body = message.get_content()
    assert link in body and "one hour" in body and "ignore this email" in body
    assert captured["endpoint"] == ("smtp.example.com", 587)
    assert captured["login"] == ("mailbox", "secret")
    assert captured["starttls"] is True
    assert mail.public_url() == "https://studyflow.example"


def test_port_465_uses_ssl(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STUDYFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("STUDYFLOW_SMTP_FROM", "noreply@example.com")
    monkeypatch.setenv("STUDYFLOW_PUBLIC_URL", "https://studyflow.example")
    monkeypatch.delenv("STUDYFLOW_SMTP_USER", raising=False)
    captured = {}

    class FakeSSL:
        def __init__(self, host, port, timeout=None):
            captured["ssl"] = (host, port)

        def login(self, user, password):
            captured["login"] = True

        def send_message(self, message):
            captured["sent"] = True

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSL)
    mail.send_reset_email("ana@example.com", "https://studyflow.example/reset?token=abc")
    assert captured["ssl"] == ("smtp.example.com", 465)
    assert captured["sent"] is True
    assert "login" not in captured
