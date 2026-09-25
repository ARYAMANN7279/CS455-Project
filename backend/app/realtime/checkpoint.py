"""Periodic CRDT checkpointing.

Writes a `document_versions` row for each active room every N seconds. This
is the bridge between the live Yjs state (in memory) and the durable store
(Postgres) that snapshot restore and version history read from.

It does NOT run on every keystroke. That would be orders of magnitude too
much load on the DB and is unnecessary — Yjs guarantees all clients converge
without our help; checkpoints are only needed for durability and reconnect
after server restart.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import DocumentVersion
from app.realtime.crdt import doc_to_bytes
from app.realtime.manager import room_manager

log = logging.getLogger(__name__)

CHECKPOINT_INTERVAL_SECONDS = 5


async def checkpoint_loop() -> None:
    while True:
        try:
            await asyncio.sleep(CHECKPOINT_INTERVAL_SECONDS)
            await _checkpoint_once()
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            log.exception("checkpoint iteration failed")


async def _checkpoint_once() -> None:
    stats = room_manager.stats()
    if stats["rooms"] == 0:
        return
    log.debug("checkpointing %d rooms", stats["rooms"])

    async with AsyncSessionLocal() as db:
        for (session_id, file_id), room in list(room_manager._rooms.items()):  # type: ignore[attr-defined]
            payload = doc_to_bytes(room.doc)
            if not payload:
                continue
            res = await db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.file_id == file_id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
            latest = res.scalar_one_or_none()
            next_version = (latest.version_number + 1) if latest else 1
            db.add(
                DocumentVersion(
                    file_id=file_id,
                    version_number=next_version,
                    snapshot_bytes=payload,
                    created_at=datetime.now(timezone.utc),
                )
            )
        await db.commit()
