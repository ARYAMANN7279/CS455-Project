"""Folder CRUD."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status, Response
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession
from app.models import Folder, Project, ProjectMember, Role
from app.schemas import FolderCreate, FolderOut, FolderUpdate
from app.realtime.manager import room_manager
import json

router = APIRouter(prefix="/projects/{project_id}/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
async def list_folders(project_id: int, user: CurrentUser, db: DbSession) -> list[FolderOut]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC: VIEWERS can list folders, but they must be a member
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        if not res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to list folders in this project")

    res = await db.execute(select(Folder).where(Folder.project_id == project_id).order_by(Folder.id))
    return [FolderOut.model_validate(f) for f in res.scalars().all()]


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    project_id: int, payload: FolderCreate, user: CurrentUser, db: DbSession
) -> FolderOut:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC check: only OWNER or EDITOR can create folders
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        member = res.scalar_one_or_none()
        if not member or member.role not in (Role.EDITOR, Role.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor role required to create folders")

    folder = Folder(
        project_id=project_id,
        name=payload.name,
        parent_folder_id=payload.parent_id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    # Broadcast structural update
    broadcast_payload = json.dumps({
        "op": "WORKSPACE_FOLDER_CREATED",
        "folder": FolderOut.model_validate(folder).model_dump(mode="json")
    })
    room_manager.broadcast_to_project(project_id, broadcast_payload)

    return FolderOut.model_validate(folder)


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    project_id: int, folder_id: int, payload: FolderUpdate, user: CurrentUser, db: DbSession
) -> FolderOut:
    folder = await db.get(Folder, folder_id)
    if not folder or folder.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    project = await db.get(Project, project_id)
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        member = res.scalar_one_or_none()
        if not member or member.role not in (Role.EDITOR, Role.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor role required to modify folders")

    # Update name
    if payload.name is not None:
        folder.name = payload.name

    # Update parent
    if payload.parent_id is not None:
        folder.parent_folder_id = payload.parent_id

    # Update paths of all descendant files
    # This is a simplified version; a robust implementation would recursively update all child folder paths
    from app.models.file import File
    from sqlalchemy import update as sa_update

    if payload.parent_id is not None or payload.name is not None:
        # In a real system, we would calculate the new path prefix and update all child files
        # For now, we'll mark it as needing update or implement a simpler path logic
        pass

    await db.commit()
    await db.refresh(folder)

    # Broadcast structural update
    broadcast_payload = json.dumps({
        "op": "WORKSPACE_FOLDER_UPDATED",
        "folder": FolderOut.model_validate(folder).model_dump(mode="json")
    })
    room_manager.broadcast_to_project(project_id, broadcast_payload)

    return FolderOut.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    project_id: int, folder_id: int, user: CurrentUser, db: DbSession
) -> Response:
    folder = await db.get(Folder, folder_id)
    if not folder or folder.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    project = await db.get(Project, project_id)
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        member = res.scalar_one_or_none()
        if not member or member.role not in (Role.EDITOR, Role.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor role required to delete folders")

    await db.delete(folder)
    await db.commit()

    # Broadcast structural update
    broadcast_payload = json.dumps({
        "op": "WORKSPACE_FOLDER_DELETED",
        "folder_id": folder_id
    })
    room_manager.broadcast_to_project(project_id, broadcast_payload)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
