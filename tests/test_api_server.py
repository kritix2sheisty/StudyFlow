"""
tests/test_api_server.py
Running the API on its own, without Reflex: `api_server` exposes the
Starlette app for uvicorn, points storage at the database the host
provides through STUDYFLOW_DB_PATH, and creates the tables on start.
The same variable lets the Reflex app use a mounted disk too.
"""

import importlib
import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import storage


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("STUDYFLOW_DB_PATH", raising=False)
    yield
    # storage.DB_PATH may have been repointed by the module under test; other suites set their own.


def test_default_db_path_is_the_repo_data_folder_unless_the_environment_says_otherwise(clean_env, monkeypatch, tmp_path):
    assert storage.default_db_path() == Path(storage.__file__).parent / "data" / "studyflow.db"
    monkeypatch.setenv("STUDYFLOW_DB_PATH", str(tmp_path / "disk" / "studyflow.db"))
    assert storage.default_db_path() == tmp_path / "disk" / "studyflow.db"


def test_api_server_points_storage_at_the_configured_database_and_creates_it(clean_env, monkeypatch, tmp_path):
    db = tmp_path / "mounted" / "studyflow.db"
    monkeypatch.setenv("STUDYFLOW_DB_PATH", str(db))
    import api_server
    importlib.reload(api_server)
    assert storage.DB_PATH == db
    assert db.exists()                                                  # init_db ran at import
    client = TestClient(api_server.app)
    assert client.get("/api/health").json() == {"status": "ok"}
    r = client.post("/api/auth/register", json={"email": "ana@example.com", "password": "a long enough password"})
    assert r.status_code == 201
    assert storage.get_user_by_email("ana@example.com") is not None    # written to the configured file


def test_api_server_uses_the_repo_database_when_nothing_is_configured(clean_env, monkeypatch, tmp_path):
    # Keep the real data folder untouched: point the default at a temp folder for this test.
    monkeypatch.setattr(storage, "default_db_path", lambda: tmp_path / "data" / "studyflow.db")
    import api_server
    importlib.reload(api_server)
    assert storage.DB_PATH == tmp_path / "data" / "studyflow.db"
    assert TestClient(api_server.app).get("/api/health").status_code == 200


def test_requirements_for_the_api_alone_do_not_include_reflex():
    text = (Path(storage.__file__).parent / "requirements-api.txt").read_text()
    names = {line.split("=")[0].split(">")[0].strip().lower() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    assert {"starlette", "uvicorn", "argon2-cffi"} <= names
    assert "reflex" not in names
