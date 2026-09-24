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

  # collector_daemon.py's own loop only catches ordinary Python exceptions --
  # it can't protect against the process itself being killed (e.g. an
  # OOM-kill), and this happened for real on 2026-08-12: the process died and
  # nothing restarted it, so live collection for every city on this daemon
  # silently stopped for six weeks before anyone noticed. Restart on any
  # exit rather than trust that it never dies.
  while true; do
    python3 collector_daemon.py || true
    echo "collector_daemon.py exited -- restarting in 10s" >&2
    sleep 10
  done
}

run_scraper_daemon() {
  # Same silent-death risk as collector_daemon.py above, even though it
  # hasn't happened yet for this one -- restart on exit here too rather than
  # wait to find out the hard way.
  while true; do
    python3 scraper_daemon.py || true
    echo "scraper_daemon.py exited -- restarting in 10s" >&2
    sleep 10
  done
}

bootstrap_and_collect &
run_scraper_daemon &

exec gunicorn --workers 2 --bind 0.0.0.0:8080 --timeout 120 app:app
