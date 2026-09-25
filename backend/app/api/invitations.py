"""Invitation API."""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import Project, Invitation, ProjectMember, Role
from app.schemas import ProjectOut

router = APIRouter(prefix="/invitations", tags=["invitations"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    project_id: int, role: str, user: CurrentUser, db: DbSession
) -> dict:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # RBAC: only owner or editor can invite
    if project.owner_id != user.id:
        res = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        member = res.scalar_one_or_none()
        if not member or member.role not in (Role.EDITOR, Role.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions to invite")

    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        project_id=project_id,
        token=token,
        role=role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    return {"token": token, "invite_url": f"/join?token={token}"}

@router.post("/accept/{token}")
async def accept_invitation(token: str, user: CurrentUser, db: DbSession):
    res = await db.execute(select(Invitation).where(Invitation.token == token))
    inv = res.scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invitation expired")

    # Grant access to the project.
    project = await db.get(Project, inv.project_id)

    # Add user to project
    member = ProjectMember(project_id=project.id, user_id=user.id, role=inv.role)
    db.add(member)

    # Delete invitation
    await db.delete(inv)

    await db.commit()
    return {"message": "Joined project successfully"}
