"""The worker's heartbeat contract — what its healthcheck relies on."""

import asyncio
import os
import time

from app import worker


def test_a_tick_completes():
    asyncio.run(worker.tick())


def test_a_fresh_heartbeat_is_healthy(tmp_path):
    hb = tmp_path / "hb"
    worker.beat(hb)
    assert worker.is_fresh(hb, max_age=60)


def test_a_stale_heartbeat_is_not(tmp_path):
    hb = tmp_path / "hb"
    worker.beat(hb)
    old = time.time() - 600
    os.utime(hb, (old, old))
    assert not worker.is_fresh(hb, max_age=60)


def test_no_heartbeat_is_not_healthy(tmp_path):
    assert not worker.is_fresh(tmp_path / "missing", max_age=60)


def test_the_loop_beats_and_stops(tmp_path, monkeypatch):
    hb = tmp_path / "hb"
    monkeypatch.setattr(worker, "HEARTBEAT", hb)
    monkeypatch.setattr(worker, "INTERVAL", 0.01)

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await task

    asyncio.run(go())
    assert worker.is_fresh(hb, max_age=60)
