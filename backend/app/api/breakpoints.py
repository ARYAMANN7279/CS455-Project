"""Breakpoint CRUD + debug session control.

Actual stepping (continue/next/stepIn) is sent over WebSocket because we want
to broadcast the resulting state to all session members; these REST endpoints
handle CRUD of breakpoint state and session lifecycle.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession, get_member
from app.models import Breakpoint, DebugSession, File, Role
from app.schemas import BreakpointOut, BreakpointUpsert

router = APIRouter(prefix="/projects/{project_id}", tags=["debug"])


async def _require_debugger(db: AsyncSession, project_id: int, user_id: int):
    member = await get_member(db, project_id, user_id)
    if Role(member.role.value if hasattr(member.role, 'value') else member.role) not in {Role.OWNER, Role.DEBUGGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requires debugger+ role"
        )
    return member


@router.get("/breakpoints", response_model=list[BreakpointOut])
async def list_breakpoints(
    project_id: int, file_id: int, user: CurrentUser, db: DbSession
) -> list[BreakpointOut]:
    await get_member(db, project_id, user.id)
    res = await db.execute(select(Breakpoint).where(Breakpoint.file_id == file_id))
    return [BreakpointOut.model_validate(b) for b in res.scalars().all()]


@router.put("/breakpoints", response_model=list[BreakpointOut])
async def upsert_breakpoints(
    project_id: int, payload: list[BreakpointUpsert], user: CurrentUser, db: DbSession
) -> list[BreakpointOut]:
    await _require_debugger(db, project_id, user.id)

    # Validate file belongs to the project.
    for bp in payload:
        file = await db.get(File, bp.file_id)
        if not file or file.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"File {bp.file_id} not found in project"
            )

    # Replace-all: simple, predictable, and matches the IDE experience (set the line set).
    if payload:
        file_ids = {bp.file_id for bp in payload}
        for fid in file_ids:
            res = await db.execute(select(Breakpoint).where(Breakpoint.file_id == fid))
            for existing in res.scalars().all():
                await db.delete(existing)

        for bp in payload:
            db.add(
                Breakpoint(
                    file_id=bp.file_id, line=bp.line, enabled=bp.enabled, created_by=user.id
                )
            )

    await db.commit()

    # Broadcast new breakpoint state to project members over the WS gateway.
    from app.realtime.manager import room_manager
    from app.realtime.execution_queue import publish_project_event

    lines_by_file: dict[int, list[int]] = {}
    if payload:
        for bp in payload:
            lines_by_file.setdefault(bp.file_id, []).append(bp.line)
    await publish_project_event(
        project_id,
        {
            "type": "breakpoints_updated",
            "lines_by_file": lines_by_file,
        },
    )
    return [
        BreakpointOut.model_validate(
            Breakpoint(
                file_id=bp.file_id, line=bp.line, enabled=bp.enabled, created_by=user.id
            )
        )
        for bp in payload
    ]


@router.post("/debug/start", response_model=dict)
async def start_debug(
    project_id: int, file_id: int, user: CurrentUser, db: DbSession
) -> dict:
    await _require_debugger(db, project_id, user.id)
    # Get file path for current_file field
    from app.models import File
    file_result = await db.get(File, file_id)
    if not file_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"File {file_id} not found"
        )

    # Create a pending debug session (execution_id will be set when execution is created)
    debug_session = DebugSession(
        execution_id=None,
        current_file=file_result.path,
        status=DebugStatus.ACTIVE
    )
    db.add(debug_session)
    await db.commit()
    await db.refresh(debug_session)

    return {
        "project_id": project_id,
        "file_id": file_id,
        "debug_session_id": debug_session.id,
        "status": "started"
    }
