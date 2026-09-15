"""
api_server.py
The StudyFlow API on its own, for a host that runs only the API (the
phones need nothing else). No Reflex: just Starlette under uvicorn.

    STUDYFLOW_DB_PATH=/data/studyflow.db uvicorn api_server:app --host 0.0.0.0 --port $PORT

Storage is pointed at STUDYFLOW_DB_PATH when set (a mounted disk on the
host), otherwise at data/studyflow.db next to this file, and the tables
are created before the first request. The routes are exactly the ones
the Reflex app mounts; nothing is added or changed here.
"""

import storage
from api import create_api

storage.set_db_path(storage.default_db_path())
storage.init_db()

app = create_api()


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8010")))
