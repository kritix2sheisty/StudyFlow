"""
tests/test_web_hosting.py
The website hosted on its own, as a client of the API hosted elsewhere.
When STUDYFLOW_API_URL is set the Reflex app must not mount its own
copy of the API: the web host would otherwise expose a second, empty
StudyFlow at /api. With the variable unset (the laptop), the API is
mounted in-process exactly as before.
"""

import os

import pytest
from starlette.applications import Starlette

import StudyFlow.StudyFlow as web


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("STUDYFLOW_API_URL", raising=False)
    yield


def test_the_api_is_mounted_in_process_when_no_api_host_is_configured():
    assert isinstance(web.api_transformer_for_this_host(), Starlette)


def test_the_api_is_not_mounted_when_the_web_app_points_at_a_hosted_api(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_API_URL", "https://studyflow-production-a60f.up.railway.app")
    assert web.api_transformer_for_this_host() is None


def test_blank_api_host_counts_as_unset(monkeypatch):
    monkeypatch.setenv("STUDYFLOW_API_URL", "   ")
    assert isinstance(web.api_transformer_for_this_host(), Starlette)


def test_the_running_app_used_the_same_rule():
    """The module built `app` at import with the environment of that moment (the laptop: unset)."""
    assert os.environ.get("STUDYFLOW_API_URL", "").strip() == ""
    assert web.app.api_transformer is not None


def test_railway_toml_does_not_force_the_api_image_on_every_service():
    """A second website service shares this repo; a pinned Dockerfile would keep shipping uvicorn."""
    from pathlib import Path
    text = (Path(web.__file__).resolve().parents[1] / "railway.toml").read_text()
    assert "dockerfilePath" not in text
    assert 'healthcheckPath = "/api/health"' not in text


def test_the_web_container_is_reflex_and_does_not_ship_the_api_server():
    """A second host runs the website; the API stays the existing Dockerfile."""
    from pathlib import Path
    root = Path(web.__file__).resolve().parents[1]
    text = (root / "Dockerfile.web").read_text()
    assert "reflex export" in text and "reflex run --env prod --backend-only" in text
    assert "api_server" not in text and "requirements-api.txt" not in text
    assert "STUDYFLOW_API_URL" in text  # documented as a runtime variable
    caddy = (root / "Caddyfile").read_text()
    assert "/_event" in caddy and "/_health" in caddy
    assert "localhost:8000" in caddy
