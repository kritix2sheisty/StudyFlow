# The StudyFlow API on its own, for a host that runs containers
# (Railway, Render and most others). No Reflex, no frontend: the phones
# only need the API. The database lives on the host's disk at
# STUDYFLOW_DB_PATH (mount a volume there); the host sets PORT.
#
#   docker build -t studyflow-api .
#   docker run -p 8010:8010 -e STUDYFLOW_DB_PATH=/data/studyflow.db -v studyflow-data:/data studyflow-api

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    STUDYFLOW_DB_PATH=/data/studyflow.db \
    PORT=8010

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Only what the API imports: the engine, storage, the API package and the
# plan-view helper the API reuses. No Reflex pages, tests or data.
COPY api_server.py storage.py models.py scheduler.py schedule_builder.py schedule_analyzer.py schedule_optimizer.py study_plan.py ./
COPY api/ api/
COPY StudyFlow/__init__.py StudyFlow/plan_view.py StudyFlow/

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8010

CMD ["sh", "-c", "uvicorn api_server:app --host 0.0.0.0 --port ${PORT}"]
