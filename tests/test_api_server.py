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


def test_dockerfile_ships_the_standalone_api_and_nothing_of_reflex():
    """The container runs api_server under uvicorn from the API-only requirements; the Reflex app stays out."""
    root = Path(storage.__file__).parent
    text = (root / "Dockerfile").read_text()
    assert "requirements-api.txt" in text and "api_server:app" in text and "STUDYFLOW_DB_PATH" in text
    instructions = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert "requirements.txt" not in " ".join(instructions).replace("requirements-api.txt", "")
    assert not any("reflex" in line.lower() for line in instructions)       # comments may mention it; steps never install it
    copied = {name for line in text.splitlines() if line.startswith("COPY ") for name in line.split()[1:-1]}
    for needed in ("api_server.py", "storage.py", "models.py", "scheduler.py", "schedule_builder.py",
                   "schedule_analyzer.py", "schedule_optimizer.py", "study_plan.py", "api/", "StudyFlow/plan_view.py"):
        assert needed in copied, needed
    assert "StudyFlow/StudyFlow.py" not in copied and "tests/" not in copied
    ignored = (root / ".dockerignore").read_text().split()
    assert "data/" in ignored and "*.db" in ignored and "mobile/" in ignored
