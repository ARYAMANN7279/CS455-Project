"""Execution endpoints: trigger, fetch status, cancel."""
from __future__ import annotations

import json
import socket
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession, get_member
from app.models import (
    Execution,
    ExecutionStatus,
    File,
    Project,
    Role,
    ProjectMember,
)
from app.realtime.execution_queue import enqueue_execution
from app.schemas import ExecutionOut, RunRequest

router = APIRouter(prefix="/projects/{project_id}/executions", tags=["executions"])


async def _require_runner(db: AsyncSession, project_id: int, user_id: int) -> ProjectMember:
    member = await get_member(db, project_id, user_id)
    if Role(member.role) not in {Role.OWNER, Role.EDITOR, Role.DEBUGGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requires editor+ role to run code"
        )
    return member


@router.post("", response_model=ExecutionOut, status_code=status.HTTP_202_ACCEPTED)
async def run_code(
    project_id: int, payload: RunRequest, user: CurrentUser, db: DbSession
) -> ExecutionOut:
    print("DEBUG: Entering run_code")
    await _require_runner(db, project_id, user.id)
    print("DEBUG: Passed _require_runner")

    debug_session = None
    file_obj = await db.get(File, payload.file_id)
    print(f"DEBUG: File found: {file_obj is not None}")
    if not file_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    print("DEBUG: Checking project")
    if file_obj.project_id != project_id:
        print("DEBUG: Project mismatch")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not belong to this project",
        )

    print("DEBUG: Accessing room manager")
    from app.realtime.manager import room_manager
    from app.realtime.crdt import doc_to_text
    from app.models import DebugSession

    # Get the current source text.
    # If the room is active (someone is editing), use the live doc.
    # Otherwise, load the latest checkpoint from the database.
    room = room_manager.get_room(project_id, payload.file_id)
    if room:
        source_text = doc_to_text(room.doc)
    else:
        from app.models import DocumentVersion
        res = await db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.file_id == payload.file_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        latest = res.scalar_one_or_none()
        if latest:
            from app.realtime.crdt import doc_from_bytes
            source_text = doc_to_text(doc_from_bytes(latest.snapshot_bytes))
        else:
            source_text = ""
    print(f"DEBUG: Source text length: {len(source_text)}")


    print("DEBUG: Creating execution record")
    execution = Execution(
        project_id=project_id,
        file_id=payload.file_id,
        status=ExecutionStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    await db.flush()
    print(f"DEBUG: Execution ID: {execution.id}")

    print("DEBUG: Checking for debug session")
    file_result = await db.get(File, payload.file_id)
    if file_result:
        pending_debug_session = await db.execute(
            select(DebugSession).where(
                DebugSession.execution_id.is_(None),
                DebugSession.current_file == file_result.path
            )
        )
        debug_session = pending_debug_session.scalar_one_or_none()
        if debug_session:
            print("DEBUG: Found pending debug session")
            debug_session.execution_id = execution.id

    await db.commit()
    await db.refresh(execution)
    print("DEBUG: Committed execution")

    is_debug = debug_session is not None
    debug_session_info = None
    if is_debug and debug_session:
        print("DEBUG: Preparing debug session info")
        from app.models import Breakpoint
        bp_result = await db.execute(
            select(Breakpoint.line).where(Breakpoint.file_id == payload.file_id)
        )
        breakpoints = [row[0] for row in bp_result.fetchall()]
        debug_session_info = {
            "file_path": debug_session.current_file,
            "breakpoints": breakpoints,
        }

    file_obj = await db.get(File, payload.file_id)
    language = file_obj.language if file_obj else "python"
    print(f"DEBUG: Language: {language}")

    print("DEBUG: Enqueueing execution")
    await enqueue_execution(
        execution_id=execution.id,
        project_id=project_id,
        file_id=payload.file_id,
        source_text=source_text,
        worker_id_hint=socket.gethostname(),
        debug=is_debug,
        debug_session_info=debug_session_info,
        language=language,
    )
    print("DEBUG: Enqueue successful")
    return ExecutionOut.model_validate(execution)


@router.get("", response_model=list[ExecutionOut])
async def list_executions(
    project_id: int, user: CurrentUser, db: DbSession
) -> list[ExecutionOut]:
    await get_member(db, project_id, user.id)
    res = await db.execute(
        select(Execution)
        .where(Execution.project_id == project_id)
        .order_by(Execution.id.desc())
        .limit(100)
    )
    return [ExecutionOut.model_validate(e) for e in res.scalars().all()]


@router.get("/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    project_id: int, execution_id: int, user: CurrentUser, db: DbSession
) -> ExecutionOut:
    await get_member(db, project_id, user.id)
    execution = await db.get(Execution, execution_id)
    if not execution or execution.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return ExecutionOut.model_validate(execution)


@router.post("/{execution_id}/cancel", response_model=ExecutionOut)
async def cancel_execution(
    project_id: int, execution_id: int, user: CurrentUser, db: DbSession
) -> ExecutionOut:
    member = await get_member(db, project_id, user.id)
    if Role(member.role) not in {Role.OWNER, Role.EDITOR, Role.DEBUGGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requires editor+ role to cancel"
        )

    execution = await db.get(Execution, execution_id)
    if not execution or execution.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    if execution.status in {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.CANCELLED,
    }:
        return ExecutionOut.model_validate(execution)

    execution.status = ExecutionStatus.CANCELLED
    execution.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(execution)

    # Signal the worker via Redis so it kills the container.
    from app.realtime.execution_queue import signal_cancel

    await signal_cancel(execution_id)
    return ExecutionOut.model_validate(execution)
