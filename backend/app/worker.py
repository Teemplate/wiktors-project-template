"""Background worker — the `worker` block. A loop with no HTTP surface.

    python -m app.worker            # run until SIGTERM
    python -m app.worker --once     # one tick, then exit (tests, cron-style use)
    python -m app.worker --check    # exit 0 if the heartbeat is fresh: the healthcheck

Put the real job in `tick()`: a scraper, a bot, a queue consumer. With the
`postgres` block present, open a session with `from .db import SessionLocal`.

**Health is a heartbeat file, not a port.** The deploy agent and the e2e suite
cannot curl a worker, so every completed tick touches a file and the Docker
healthcheck (`--check`) fails once it is older than three intervals. A worker
that is running but stuck — the failure that matters — goes unhealthy, where a
"process exists" check would stay green forever.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time
from pathlib import Path

from .config import settings

log = logging.getLogger("worker")

HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker-heartbeat"))
INTERVAL = float(os.environ.get("WORKER_INTERVAL_SECONDS", "30"))


async def tick() -> None:
    """One unit of work. Replace the body; keep it idempotent."""
    log.info("tick from %s", settings.app_name)


# Defaults are read at call time, not bound at import, so tests (and anything
# else) can repoint HEARTBEAT and INTERVAL.
def beat(path: Path | None = None) -> None:
    (path or HEARTBEAT).write_text(f"{time.time():.0f}\n")


def is_fresh(path: Path | None = None, max_age: float | None = None) -> bool:
    try:
        age = time.time() - (path or HEARTBEAT).stat().st_mtime
        return age < (max_age if max_age is not None else 3 * INTERVAL)
    except FileNotFoundError:
        return False


async def run(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await tick()
            beat()
        except Exception:
            # A failed tick does not beat, so a job that fails every time goes
            # unhealthy after three intervals instead of crash-looping.
            log.exception("tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL)
        except asyncio.TimeoutError:
            pass


async def _main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker started; interval %ss", INTERVAL)
    await run(stop)
    log.info("worker stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one tick and exit")
    parser.add_argument("--check", action="store_true", help="exit 0 if the heartbeat is fresh")
    args = parser.parse_args()

    if args.check:
        return 0 if is_fresh() else 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        asyncio.run(tick())
        beat()
        return 0
    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
