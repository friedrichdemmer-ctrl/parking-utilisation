#!/bin/sh
set -e

DB_PATH="${PARKING_DB_PATH:-/data/parking.db}"
ARCHIVE_PATH="${PARKING_ARCHIVE_PATH:-/data/parking-data-archive}"

mkdir -p "$(dirname "$DB_PATH")"

# Bootstraps the DB (if missing) and then starts the live collector loop, all
# in the background so gunicorn can bind immediately and pass health checks
# instead of blocking traffic for the ~10-20 minute first-boot import.
bootstrap_and_collect() {
  if [ ! -f "$DB_PATH" ]; then
    echo "No database found at $DB_PATH -- bootstrapping from the public archive."
    echo "This is a one-time step and takes roughly 10-20 minutes depending on machine size."

    if [ ! -d "$ARCHIVE_PATH" ]; then
      git clone --depth 1 https://github.com/defgsus/parking-data.git "$ARCHIVE_PATH"
    fi

    python3 import_historical.py
    python3 recluster.py
    echo "Bootstrap complete: $DB_PATH is ready."
  fi

  python3 collector_daemon.py
}

bootstrap_and_collect &

exec gunicorn --workers 2 --bind 0.0.0.0:8080 --timeout 120 app:app
