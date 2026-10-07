import os
import sys
from pathlib import Path

import reflex as rx

# Reflex's dev reloader watches every top-level entry of the project.
# The database lives in data/, and a write there must not restart the
# backend: each restart drops connections and in-memory state, which
# showed up as connection resets and rolled-back state during testing.
# Hidden directories (.states, .logs, .web) are excluded by Reflex
# itself. This is read before the reloader starts, so it takes effect
# for `reflex run`; an explicit environment variable still wins.
os.environ.setdefault("REFLEX_HOT_RELOAD_EXCLUDE_PATHS", "data")


def _load_dotenv(path: Path) -> None:
    """KEY=value lines from a gitignored .env, without overriding a real environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


# pytest must not pick up a laptop .env pointed at Railway: those tests
# expect an in-process API. `reflex run` loads this file first, so the
# website sees STUDYFLOW_API_URL before the app module is imported.
if "pytest" not in sys.modules and not os.environ.get("PYTEST_VERSION"):
    _load_dotenv(Path(__file__).parent / ".env")

config = rx.Config(
    app_name="StudyFlow",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ]
)
