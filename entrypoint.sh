#!/bin/bash
set -e

echo "[ENTRYPOINT] Running database migrations..."
alembic upgrade head
echo "[ENTRYPOINT] Migrations complete. Starting uvicorn..."

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --loop uvloop \
    --http httptools
