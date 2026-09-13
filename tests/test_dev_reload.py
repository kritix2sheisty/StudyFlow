"""
tests/test_dev_reload.py
The dev server must not restart when the database changes. Reflex's
reloader watches every top-level entry of the project; rxconfig.py
excludes data/ (where the database lives) before the reloader starts.
"""

import importlib
import os

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("REFLEX_HOT_RELOAD_EXCLUDE_PATHS", raising=False)
    yield


def test_rxconfig_excludes_the_data_directory_from_reload(clean_env):
    import rxconfig
    importlib.reload(rxconfig)                       # apply the setdefault with a clean environment
    assert os.environ["REFLEX_HOT_RELOAD_EXCLUDE_PATHS"] == "data"
    from reflex.utils.exec import get_reload_paths
    watched = {p.name for p in get_reload_paths()}
    assert "data" not in watched
    assert {"StudyFlow", "api", "storage.py", "study_plan.py"} <= watched   # code is still watched


def test_an_explicit_environment_setting_still_wins(monkeypatch):
    monkeypatch.setenv("REFLEX_HOT_RELOAD_EXCLUDE_PATHS", "tests")
    import rxconfig
    importlib.reload(rxconfig)
    assert os.environ["REFLEX_HOT_RELOAD_EXCLUDE_PATHS"] == "tests"
