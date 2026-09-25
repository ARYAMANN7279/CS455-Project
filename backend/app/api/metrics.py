"""Metrics endpoints — for the dashboard in Feature 12.

We expose simple, cheap-to-compute aggregates. The metrics dashboard reads
these (and structured logs) to render charts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.deps import DbSession
from app.models import Execution, ExecutionEvent, ExecutionStatus

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/executions/summary")
async def execution_summary(db: DbSession) -> dict:
    res = await db.execute(
        select(Execution.status, func.count(Execution.id)).group_by(Execution.status)
    )
    counts = {status.value: count for status, count in res.all()}

    res_dur = await db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch", Execution.finished_at - Execution.started_at
                )
            )
        ).where(
            Execution.started_at.is_not(None),
            Execution.finished_at.is_not(None),
        )
    )
    avg_runtime_seconds = float(res_dur.scalar() or 0.0)

    return {
        "status_counts": counts,
        "avg_runtime_seconds": round(avg_runtime_seconds, 4),
    }


@router.get("/executions/last_hour")
async def executions_last_hour(db: DbSession) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    res = await db.execute(
        select(func.count(Execution.id)).where(Execution.queued_at >= cutoff)
    )
    return {"last_hour": res.scalar() or 0}


@router.get("/events/recent")
async def recent_events(db: DbSession, limit: int = 100) -> dict:
    res = await db.execute(
        select(ExecutionEvent)
        .order_by(ExecutionEvent.id.desc())
        .limit(limit)
    )
    events = [
        {
            "id": e.id,
            "execution_id": e.execution_id,
            "event_type": e.event_type,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
        }
        for e in res.scalars().all()
    ]
    return {"events": events}
