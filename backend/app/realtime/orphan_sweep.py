"""Orphan sweep loop for detecting and handling crashed workers.

Periodically checks for executions stuck in STARTING or RUNNING state
when their associated worker has likely crashed, and marks them as FAILED.
"""

import asyncio
from datetime import datetime, timedelta
import logging

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Execution, ExecutionStatus

log = logging.getLogger(__name__)


async def sweep_orphans() -> None:
    """Background task that sweeps for orphaned executions.

    Runs every 60 seconds to check for executions that have been in
    STARTING or RUNNING state for more than 5 minutes, indicating
    the worker likely crashed.
    """
    while True:
        try:
            await asyncio.sleep(60)  # Run every minute

            # Define threshold: executions older than 5 minutes
            threshold_time = datetime.utcnow() - timedelta(minutes=5)

            async with AsyncSessionLocal() as db:
                # Find executions stuck in starting or running state
                # Use .value to get the string value of the enum, not the name
                print("DEBUG: About to query for orphaned executions")  # DEBUG
                stmt = select(Execution).where(
                    Execution.status.in_([ExecutionStatus.STARTING.value, ExecutionStatus.RUNNING.value]),
                    Execution.started_at < threshold_time
                )
                print(f"DEBUG: Statement compiled: {stmt}")  # DEBUG

                result = await db.execute(stmt)
                orphaned_executions = result.scalars().all()
                print(f"DEBUG: Found {len(orphaned_executions)} orphaned executions")  # DEBUG

                for execution in orphaned_executions:
                    log.warning(
                        "Found orphaned execution %d (status: %s, started: %s), "
                        "marking as failed due to worker death",
                        execution.id, execution.status.value, execution.started_at
                    )

                    # Mark as failed
                    execution.status = ExecutionStatus.FAILED
                    execution.finished_at = datetime.utcnow()
                    execution.stderr = "Worker died mid-execution (orphan sweep)"

                    db.add(execution)

                if orphaned_executions:
                    await db.commit()
                    log.info("Marked %d orphaned executions as failed",
                           len(orphaned_executions))

        except Exception as e:
            log.error("Error in orphan sweep: %s", e, exc_info=True)
            # Continue the loop even if there's an error
            await asyncio.sleep(60)
