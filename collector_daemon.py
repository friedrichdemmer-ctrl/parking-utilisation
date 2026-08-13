#!/usr/bin/env python3
"""Run collector.collect() forever, every 30 minutes.

Hosted platforms like Fly.io/Railway don't ship a built-in cron, and the app
runs as a persistent process there (unlike the local launchd job), so this
loop takes over the "every 30 minutes" job in production.
"""

import time
import traceback

import collector

INTERVAL_SECONDS = 1800


def main() -> None:
    while True:
        try:
            collector.collect()
        except Exception:
            traceback.print_exc()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
