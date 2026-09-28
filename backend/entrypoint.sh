#!/usr/bin/env bash
set -e

# Bring the schema to the latest revision before serving any traffic.
echo "Applying database migrations..."
alembic upgrade head

# Optionally seed demo data on first boot (set SEED_ON_START=true in the env).
if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "Seeding demo data..."
  python -m app.scripts.seed || echo "Seed skipped/failed (continuing)."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"
