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
