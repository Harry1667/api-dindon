#!/bin/bash
set -e

echo "Running Alembic migrations..."
alembic upgrade head || echo "WARNING: Alembic migration failed, continuing..."

echo "Starting application..."
exec "$@"
