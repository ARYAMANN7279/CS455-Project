"""AI Assistant schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_assistant import AIProvider


class AIAssistantConfigBase(BaseModel):
    """Base AI assistant configuration."""
    provider: AIProvider
    model_name: Optional[str] = Field(None, max_length=100)


class AIAssistantConfigCreate(AIAssistantConfigBase):
    """Create AI assistant configuration."""
    api_key: str = Field(min_length=10)


class AIAssistantConfigUpdate(BaseModel):
    """Update AI assistant configuration."""
    provider: Optional[AIProvider] = None
    model_name: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = Field(None, min_length=10)
    is_active: Optional[bool] = None


class AIAssistantConfigOut(AIAssistantConfigBase):
    """AI assistant configuration response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AIAssistantRequestBase(BaseModel):
    """Base AI assistant request."""
    prompt: str = Field(min_length=1, max_length=8000)  # Reasonable limit


class AIAssistantRequestCreate(AIAssistantRequestBase):
    """Create AI assistant request."""
    context_code: Optional[str] = Field(None, description="The current content of the active file in the editor")


class AIAssistantRequestOut(BaseModel):
    """AI assistant request/response log."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    prompt: str
    response: str
    provider: AIProvider
    model_used: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    latency_ms: Optional[int]
    is_successful: bool
    error_message: Optional[str]
    created_at: datetime


class AIDiffProposal(BaseModel):
    """A proposed change to a file."""
    original_text: str
    proposed_text: str
    explanation: Optional[str] = None

class AIAssistantResponse(BaseModel):
    """AI assistant response."""
    response: str
    provider: AIProvider
    model_used: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    proposal: Optional[AIDiffProposal] = None
