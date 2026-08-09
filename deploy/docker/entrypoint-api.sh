#!/bin/sh
set -eu
alembic upgrade head
exec uvicorn apps.api.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log
