"""
tests/test_dashboard.py
A smoke test for the Reflex pages: each one builds, and the state
exposes the vars the pages bind to. This does not start a browser;
it catches the errors that would stop reflex run before it serves
anything.
"""

from pathlib import Path

from StudyFlow.StudyFlow import (
    DashboardState, app, assignments_page, focus_page, index, login_page, progress_page, register_page,
    schedule_page, share_site_url,
)


def test_every_page_builds():
    for page in (index, assignments_page, schedule_page, progress_page, focus_page, login_page, register_page):
        assert page() is not None
    assert app is not None


def test_state_exposes_the_vars_the_pages_bind_to():
    for name in (
        "assignments", "assignment_count", "required_hours", "greeting", "today_label",
        "completed_names", "completed_count",
        "slots", "slot_hours",
        "has_plan", "plan_stale", "plan_message", "plan_days", "today_plan", "plan_statuses",
        "plan_required", "plan_scheduled", "plan_unscheduled", "plan_completion", "progress_value",
        "authenticated", "user_email", "auth_email", "auth_password", "auth_confirm", "auth_error",
        "saved_token", "import_available", "import_summary", "share_open",
    ):
        assert hasattr(DashboardState, name), name


def test_no_sample_data_module_remains():
    import importlib.util
    assert importlib.util.find_spec("StudyFlow.sample_data") is None


def test_share_site_url_defaults_to_the_hosted_website(monkeypatch):
    monkeypatch.delenv("STUDYFLOW_PUBLIC_URL", raising=False)
    assert share_site_url() == "https://studyflow-production-d5e4.up.railway.app"
    monkeypatch.setenv("STUDYFLOW_PUBLIC_URL", "https://studyflow.example/")
    assert share_site_url() == "https://studyflow.example"


def test_logo_and_share_qr_are_in_assets():
    root = Path(__file__).resolve().parents[1] / "assets"
    assert (root / "logo.png").read_bytes().startswith(b"\x89PNG")
    assert (root / "favicon.ico").is_file()
    qr = (root / "share-qr.svg").read_text(encoding="utf-8")
    assert "<svg" in qr and "path" in qr


def test_brand_theme_stylesheet_is_loaded():
    css = (Path(__file__).resolve().parents[1] / "assets" / "studyflow.css").read_text(encoding="utf-8")
    assert "--indigo-9: #2B2F9D" in css and "Fraunces" in css and ".sf-hero" in css
    assert "/studyflow.css" in app.stylesheets


def test_padding_and_margin_use_units():
    # Emotion passes "4" through as-is, which the browser drops; Radix space tokens need var(--space-4).
    import re
    src = (Path(__file__).resolve().parents[1] / "StudyFlow" / "StudyFlow.py").read_text(encoding="utf-8")
    assert not re.search(r'\b(?:padding|margin)\w*=(?:"\d"|rx\.breakpoints\([^)]*"\d")', src)
