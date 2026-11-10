#!/bin/sh
set -eu

mkdir -p /app/data /app/corpus/index

python -m scout.cli init
python -m scout.cli ingest

exec python -m scout.cli serve --host 0.0.0.0 --port "${PORT:-8000}"
