"""Snapshots: create a labeled checkpoint, list, restore."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession, get_member
from app.models import (
    File,
    Project,
    Role,
    ProjectMember,
    Snapshot,
    SnapshotFile,
)
from app.realtime.crdt import doc_from_bytes, doc_to_bytes
from app.realtime.manager import room_manager
from app.schemas import SnapshotCreate, SnapshotOut
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/projects/{project_id}/snapshots", tags=["snapshots"])


async def _require_owner_or_editor(db: AsyncSession, project_id: int, user_id: int) -> ProjectMember:
    member = await get_member(db, project_id, user_id)
    if Role(member.role.value if hasattr(member.role, 'value') else member.role) not in {Role.OWNER, Role.EDITOR, Role.DEBUGGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requires editor+ role"
        )
    return member


@router.post("", response_model=SnapshotOut, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    project_id: int, payload: SnapshotCreate, user: CurrentUser, db: DbSession
) -> SnapshotOut:
    await _require_owner_or_editor(db, project_id, user.id)

    snapshot = Snapshot(project_id=project_id, label=payload.label, created_by=user.id)
    db.add(snapshot)
    await db.flush()

    res = await db.execute(select(File).where(File.project_id == project_id))
    for f in res.scalars().all():
        room = room_manager.get_room(project_id, f.id)
        if room is None:
            continue
        content = doc_to_bytes(room.doc)
        db.add(SnapshotFile(snapshot_id=snapshot.id, file_id=f.id, content=content))

    await db.commit()
    await db.refresh(snapshot)
    return SnapshotOut.model_validate(snapshot)


@router.get("", response_model=list[SnapshotOut])
async def list_snapshots(
    project_id: int, user: CurrentUser, db: DbSession
) -> list[SnapshotOut]:
    await get_member(db, project_id, user.id)
    res = await db.execute(
        select(Snapshot).where(Snapshot.project_id == project_id).order_by(Snapshot.id.desc())
    )
    return [SnapshotOut.model_validate(s) for s in res.scalars().all()]


@router.post("/{snapshot_id}/restore", status_code=status.HTTP_202_ACCEPTED)
async def restore_snapshot(
    project_id: int, snapshot_id: int, user: CurrentUser, db: DbSession
) -> dict:
    await _require_owner_or_editor(db, project_id, user.id)

    snapshot = await db.get(
        Snapshot,
        snapshot_id,
        options=[selectinload(Snapshot.files)],
    )
    if not snapshot or snapshot.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    restored = 0
    for sf in snapshot.files:
        # Apply the bytes to a fresh doc and rebroadcast the resulting state.
        new_doc = doc_from_bytes(sf.content)
        await room_manager.replace_document(project_id, sf.file_id, new_doc)
        restored += 1

    return {"snapshot_id": snapshot_id, "restored_files": restored}
