"""Queue + pub/sub helpers around Redis (and RQ if you choose it).

We use Redis directly for two reasons:
  1. Pub/sub is needed to broadcast execution events to all connected clients
     in a session — including across multiple backend processes if you scale out.
  2. RQ/Celery is just a wrapper around Redis lists. For a course project, a
     direct Redis list with BRPOP is two lines and removes a dependency.

The actual worker (worker/worker.py) pulls from the same queue.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Any

import redis.asyncio as aioredis
from redis import Redis

from app.core.config import get_settings

log = logging.getLogger(__name__)

QUEUE_NAME = "concord:executions"
CANCEL_CHANNEL_PREFIX = "concord:cancel:"
EXEC_EVENT_CHANNEL_PREFIX = "concord:exec:"  # pub/sub to room gateway
PRESENCE_CHANNEL_PREFIX = "concord:presence:"  # cross-process awareness


def _redis_sync() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=False)


_async_redis: aioredis.Redis | None = None


def async_redis() -> aioredis.Redis:
    global _async_redis
    if _async_redis is None:
        _async_redis = aioredis.from_url(get_settings().redis_url, decode_responses=False)
    return _async_redis


def enqueue_execution_sync(
    execution_id: int,
    project_id: int,
    file_id: int,
    source_text: str,
    worker_id_hint: str | None = None,
    debug: bool = False,
    debug_session_info: dict | None = None,
    language: str = "python",
) -> None:
    """Synchronous enqueue — used from REST handlers and from worker entry points."""
    payload = {
        "execution_id": execution_id,
        "project_id": project_id,
        "file_id": file_id,
        "source_text": source_text,
        "worker_id_hint": worker_id_hint or socket.gethostname(),
        "debug": debug,
        "debug_session_info": debug_session_info,
        "language": language,
    }
    r = _redis_sync()
    r.lpush(QUEUE_NAME, json.dumps(payload).encode("utf-8"))


async def enqueue_execution(
    execution_id: int,
    project_id: int,
    file_id: int,
    source_text: str,
    worker_id_hint: str | None = None,
    debug: bool = False,
    debug_session_info: dict | None = None,
    language: str = "python",
) -> None:
    # FastAPI handlers may be sync or async; we expose both.
    await asyncio.to_thread(
        enqueue_execution_sync,
        execution_id,
        project_id,
        file_id,
        source_text,
        worker_id_hint,
        debug,
        debug_session_info,
        language,
    )


async def signal_cancel(execution_id: int) -> None:
    """Publish on the cancel channel. The running worker subscribes and kills the container."""
    r = async_redis()
    await r.publish(CANCEL_CHANNEL_PREFIX + str(execution_id), b"1")


async def publish_project_event(project_id: int, event: dict[str, Any]) -> None:
    """Used by execution workers to broadcast stdout/stderr/status to all connected clients
    in the project. The collab gateway subscribes to this channel and forwards to its room."""
    r = async_redis()
    await r.publish(EXEC_EVENT_CHANNEL_PREFIX + str(project_id), json.dumps(event).encode("utf-8"))


async def subscribe_project_events(project_id: int):
    """Async generator of (channel, bytes) — used by the WS gateway to forward to clients."""
    import logging
    log = logging.getLogger(__name__)
    log.info("Subscribing to project events for project %d", project_id)
    r = async_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(EXEC_EVENT_CHANNEL_PREFIX + str(project_id))
    log.info("Subscribed to channel %s", EXEC_EVENT_CHANNEL_PREFIX + str(project_id))
    try:
        async for msg in pubsub.listen():
            log.debug("Received pubsub message: %s", msg)
            if msg.get("type") != "message":
                continue
            yield msg["data"]
    finally:
        log.info("Unsubscribing from project events for project %d", project_id)
        await pubsub.unsubscribe()
        await pubsub.close()
