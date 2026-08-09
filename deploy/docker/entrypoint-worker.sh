#!/bin/sh
set -eu
exec python -m inspection_platform.worker.cli serve
