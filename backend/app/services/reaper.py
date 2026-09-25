"""
Background service to clean up orphan executions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Execution, ExecutionStatus
from app.realtime.execution_queue import signal_cancel

log = logging.getLogger(__name__)

class ExecutionReaper:
    """
    The Reaper identifies 'orphan' executions—jobs that are marked as
    RUNNING or STARTING in the DB but have exceeded a reasonable timeout
    and are likely stuck or abandoned.
    """

    def __init__(self, orphan_threshold_seconds: int = 600):
        self.orphan_threshold = orphan_threshold_seconds

    async def sweep(self, session: AsyncSession) -> int:
        """
        Scans for orphan executions and signals the worker to kill them.
        Returns the number of executions reaped.
        """
        now = datetime.now(timezone.utc)
        threshold_time = now - timedelta(seconds=self.orphan_threshold)

        # Find executions that are still 'active' but are older than the threshold
        stmt = select(Execution).where(
            and_(
                Execution.status.in_({ExecutionStatus.STARTING, ExecutionStatus.RUNNING}),
                Execution.queued_at <= threshold_time
            )
        )

        result = await session.execute(stmt)
        orphans = result.scalars().all()

        if not orphans:
            return 0

        log.info("Reaper: Found %d orphan executions to sweep", len(orphans))

        for exec_obj in orphans:
            try:
                # 1. Mark as CANCELLED in DB
                exec_obj.status = ExecutionStatus.CANCELLED
                exec_obj.finished_at = now

                # 2. Signal the worker to kill the container immediately
                await signal_cancel(exec_obj.id)

                log.debug("Reaper: Signaled cancellation for execution %d", exec_obj.id)
            except Exception as e:
                log.error("Reaper: Failed to reap execution %d: %s", exec_obj.id, e)

        await session.commit()
        return len(orphans)

    async def run_forever(self, session_factory: Any, interval: int = 300):
        """Background loop that periodically runs the sweep."""
        log.info("Execution Reaper started (interval=%ds, threshold=%ds)",
                 interval, self.orphan_threshold)
        while True:
            try:
                async for session in session_factory():
                    count = await self.sweep(session)
                    if count > 0:
                        log.info("Reaper: Successfully reaped %d orphan executions", count)
                    break
            except Exception:
                log.exception("Execution Reaper loop crashed")

            await asyncio.sleep(interval)
