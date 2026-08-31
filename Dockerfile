FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CASSANDRA_WORKDIR=/tmp/cassandra

WORKDIR /app

COPY requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt

COPY cassandra ./cassandra
COPY demo ./demo

# Cloud Run supplies PORT. Keep one worker: the audit holds process level state
# (the event bus and the in flight lock) that a second worker would not see.
CMD exec uvicorn cassandra.service.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
