"""Pydantic schemas (request/response models)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --- Auth ---


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: EmailStr
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut

# --- Project ---


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    name: str
    created_at: datetime

# --- Folder ---


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None


class FolderUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    parent_folder_id: int | None
    name: str
    created_at: datetime

# --- Session ---


class SessionCreate(BaseModel):
    """Open a new collab session for a project. Creator becomes the owner."""


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    created_by: int | None
    status: str
    created_at: datetime


class SessionMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: int
    user_id: int
    role: str
    joined_at: datetime


class ProjectMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user: UserOut
    role: str


class JoinSessionOut(BaseModel):
    session: SessionOut
    role: str


class RoleUpdate(BaseModel):
    role: Literal["viewer", "editor", "debugger", "owner"]

# --- File ---


class FileCreate(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    folder_id: int | None = None


class FileUpdate(BaseModel):
    path: str | None = Field(default=None, min_length=1, max_length=512)
    folder_id: int | None = None


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    folder_id: int | None
    path: str
    language: str | None = "python"
    created_at: datetime

# --- Snapshot ---


class SnapshotCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    label: str
    created_at: datetime

# --- Execution ---


class RunRequest(BaseModel):
    file_id: int

class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int | None
    file_id: int
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    worker_id: str | None

# --- Breakpoint ---


class BreakpointUpsert(BaseModel):
    file_id: int
    line: int = Field(ge=0)
    enabled: bool = True

class BreakpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_id: int
    line: int
    enabled: bool
    created_by: int | None
    created_at: datetime

# --- Debug ---


class DebugCommand(BaseModel):
    command: Literal["continue", "next", "stepIn", "stepOut", "pause"]

# --- AI Assistant ---


from .assistant import (  # noqa: E402
    AIAssistantConfigBase,
    AIAssistantConfigCreate,
    AIAssistantConfigOut,
    AIAssistantConfigUpdate,
    AIAssistantResponse,
    AIAssistantRequestBase,
    AIAssistantRequestCreate,
    AIAssistantRequestOut,
)
