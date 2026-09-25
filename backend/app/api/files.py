"""File CRUD inside a project. The actual live editing happens over WebSocket; these
endpoints bootstrap the file (initial state) and let the frontend read the latest
checkpointed content if no live session is available."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUser, DbSession
from app.models import DocumentVersion, File, Project, ProjectMember, Role, Folder
from app.schemas import FileCreate, FileOut, FileUpdate
from app.realtime.manager import room_manager
import json

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])


@router.post("", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def create_file(
    project_id: int, payload: FileCreate, user: CurrentUser, db: DbSession
) -> FileOut:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC check: only OWNER or EDITOR can create files
    member = None
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        member = res.scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create files in this project")
        if member.role not in (Role.EDITOR, Role.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor role required to create files")

    # Derive full path based on folder
    path = payload.path
    if payload.folder_id:
        folder = await db.get(Folder, payload.folder_id)
        if not folder or folder.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found in project")

        # In a real system, we'd recursively get the parent folder paths
        # For now, we use a simplified approach or store the full path in the folder
        # Since we want a proper tree, we'll assume the frontend provides the relative path from root or we derive it here.
        # For this implementation, we'll trust the provided path but link the folder_id.
        pass

    from app.runtime.registry import get_language_from_file_path

    file = File(
        project_id=project_id,
        folder_id=payload.folder_id,
        path=path,
        language=get_language_from_file_path(path),
    )
    db.add(file)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A file with that path already exists"
        ) from exc
    await db.refresh(file)

    # Broadcast structural update
    broadcast_payload = json.dumps({
        "op": "WORKSPACE_FILE_CREATED",
        "file": FileOut.model_validate(file).model_dump(mode="json")
    })
    room_manager.broadcast_to_project(project_id, broadcast_payload)

    return FileOut.model_validate(file)


@router.get("", response_model=list[FileOut])
async def list_files(
    project_id: int, user: CurrentUser, db: DbSession
) -> list[FileOut]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC check: VIEWERS can list files, but they must be a member
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        if not res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to list files in this project")

    res = await db.execute(select(File).where(File.project_id == project_id).order_by(File.id))
    return [FileOut.model_validate(f) for f in res.scalars().all()]


@router.patch("/{file_id}", response_model=FileOut)
async def update_file(
    project_id: int, file_id: int, payload: FileUpdate, user: CurrentUser, db: DbSession
) -> FileOut:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC check: only OWNER or EDITOR can rename/move files
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        member = res.scalar_one_or_none()
        if not member or member.role not in (Role.EDITOR, Role.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor role required to update files")

    file = await db.get(File, file_id)
    if not file or file.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if payload.path is not None:
        file.path = payload.path
        # Update language based on new extension
        try:
            from app.runtime.registry import get_language_from_file_path
            file.language = get_language_from_file_path(payload.path)
        except ValueError:
            # Default to plaintext or keep existing if extension is unsupported
            pass

    if payload.folder_id is not None:
        file.folder_id = payload.folder_id

    await db.commit()
    await db.refresh(file)

    # Broadcast structural update
    broadcast_payload = json.dumps({
        "op": "WORKSPACE_FILE_UPDATED",
        "file": FileOut.model_validate(file).model_dump(mode="json")
    })
    room_manager.broadcast_to_project(project_id, broadcast_payload)

    return FileOut.model_validate(file)


@router.get("/{file_id}/content")
async def get_latest_content(
    project_id: int, file_id: int, user: CurrentUser, db: DbSession
) -> dict:
    """Return the most recent CRDT checkpoint as plain text.

    Live editing is over WebSocket; this endpoint is for cold-load and version history.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC check: VIEWERS can read content
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        if not res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access file content in this project")

    file = await db.get(File, file_id)
    if not file or file.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    res = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.file_id == file_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    latest = res.scalar_one_or_none()
    if not latest:
        return {"file_id": file_id, "text": "", "version": 0}

    # Decode the CRDT bytes back to plain text. We import lazily so the API works
    # even if pycrdt is being mocked in tests.
    from app.realtime.crdt import doc_from_bytes, doc_to_text

    doc = doc_from_bytes(latest.snapshot_bytes)
    return {
        "file_id": file_id,
        "text": doc_to_text(doc),
        "version": latest.version_number,
    }
