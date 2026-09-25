"""AI Assistant endpoints."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession, get_member
from app.core.config import get_settings

from app.llm.manager import llm_manager
from app.models import AIAssistantConfig, AIAssistantRequest, AIProvider, Project, User
from app.realtime.execution_queue import publish_project_event
from app.services.sandbox import sandbox as sandbox_runner
from app.schemas.assistant import (
    AIAssistantConfigCreate,
    AIAssistantConfigOut,
    AIAssistantConfigUpdate,
    AIAssistantRequestCreate,
    AIAssistantRequestOut,
    AIAssistantResponse,
)

log = logging.getLogger(__name__)


def sanitize_ai_output(text: str) -> str:
    """Return the AI response as-is.

    Previously, this stripped markdown fences, which removed the AI's
    explanations and analysis.
    """
    return text


router = APIRouter(prefix="/projects/{project_id}/assist", tags=["assistant"])


async def _get_project_config(
    project_id: int, db: AsyncSession
) -> AIAssistantConfig:
    """Get AI assistant configuration for a project."""
    result = await db.execute(
        select(AIAssistantConfig).where(AIAssistantConfig.project_id == project_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI assistant not configured for this project",
        )
    return config


@router.post("/config", response_model=AIAssistantConfigOut)
async def configure_assistant(
    project_id: int,
    payload: AIAssistantConfigCreate,
    user: CurrentUser,
    db: DbSession,
) -> AIAssistantConfigOut:
    """Configure AI assistant for a project."""
    if not get_settings().ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Assistant is currently disabled",
        )

    member = await get_member(db, project_id, user.id)
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if project.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project owner can configure AI assistant",
        )

    if not llm_manager.validate_provider_config(payload.provider.value, payload.api_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider configuration or API key",
        )

    result = await db.execute(
        select(AIAssistantConfig).where(AIAssistantConfig.project_id == project_id)
    )
    existing_config = result.scalar_one_or_none()

    if existing_config:
        existing_config.provider = payload.provider
        existing_config.encrypted_api_key = llm_manager._encrypt_api_key(payload.api_key)
        existing_config.model_name = payload.model_name
        existing_config.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing_config)
        config = existing_config
    else:
        config = AIAssistantConfig(
            project_id=project_id,
            provider=payload.provider,
            encrypted_api_key=llm_manager._encrypt_api_key(payload.api_key),
            model_name=payload.model_name,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

    return AIAssistantConfigOut.model_validate(config)


@router.get("/config", response_model=AIAssistantConfigOut)
async def get_assistant_config(
    project_id: int, user: CurrentUser, db: DbSession
) -> AIAssistantConfigOut:
    """Get AI assistant configuration for a project."""
    if not get_settings().ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Assistant is currently disabled",
        )
    await get_member(db, project_id, user.id)

    config = await _get_project_config(project_id, db)
    return AIAssistantConfigOut.model_validate(config)


@router.patch("/config", response_model=AIAssistantConfigOut)
async def update_assistant_config(
    project_id: int,
    payload: AIAssistantConfigUpdate,
    user: CurrentUser,
    db: DbSession,
) -> AIAssistantConfigOut:
    """Update AI assistant configuration for a project."""
    if not get_settings().ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Assistant is currently disabled",
        )
    member = await get_member(db, project_id, user.id)
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if project.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project owner can configure AI assistant",
        )

    config = await _get_project_config(project_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    if "api_key" in update_data and update_data["api_key"]:
        provider = update_data.get("provider", config.provider.value)
        if not llm_manager.validate_provider_config(provider, update_data["api_key"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid API key for provider",
            )
        update_data["encrypted_api_key"] = llm_manager._encrypt_api_key(
            update_data.pop("api_key")
        )
    if "provider" in update_data:
        update_data["provider"] = AIProvider(update_data["provider"])

    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)

    return AIAssistantConfigOut.model_validate(config)


@router.post("", response_model=AIAssistantResponse)
async def request_assistant(
    project_id: int,
    payload: AIAssistantRequestCreate,
    user: CurrentUser,
    db: DbSession,
) -> AIAssistantResponse:
    """Request AI assistant completion."""
    if not get_settings().ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Assistant is currently disabled",
        )

    allowed, rate_limit_info = llm_manager.check_rate_limit(project_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI assistant rate limit exceeded. Limit: {rate_limit_info['limit']} requests per {rate_limit_info['reset_time']} seconds.",
            headers={
                "X-RateLimit-Limit": str(rate_limit_info["limit"]),
                "X-RateLimit-Remaining": str(rate_limit_info["remaining"]),
                "X-RateLimit-Reset": str(rate_limit_info["reset_time"]),
            }
        )

    start_time = time.time()
    await get_member(db, project_id, user.id)

    try:
        config = await _get_project_config(project_id, db)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI assistant not configured for this project.",
        )

    if not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI assistant is disabled for this project",
        )

    try:
        api_key = llm_manager._decrypt_api_key(config.encrypted_api_key)
    except Exception as e:
        log.error(f"Failed to decrypt API key for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI assistant configuration error",
        )

    try:
        provider = llm_manager.get_provider(config.provider.value, api_key)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # ENHANCED SYSTEM PROMPT
    system_prompt = """You are an expert AI coding assistant. Your goal is to help users write,
    debug, and improve code.

    When a user asks about errors or bugs:
    1. Clearly identify the line(s) where the error occurs.
    2. Explain WHY it is an error (e.g., SyntaxError, Logic error, Type mismatch).
    3. Provide the corrected version of the code.
    4. Use markdown code blocks with the appropriate language tag (e.g., ```python).

    If you are suggesting a specific replacement for existing code, you MUST also provide a proposal in this JSON format at the end of your response:
    {
      "proposal": {
        "original": "the exact lines of code you are replacing",
        "proposed": "the new code to put in its place",
        "explanation": "briefly why this change is needed"
      }
    }

    Keep your explanations concise but technically accurate. Do not just repeat the code; analyze it."""

    final_prompt = payload.prompt
    if payload.context_code:
        final_prompt = (
            f"### IMPORTANT: ACTIVE EDITOR CONTEXT (READ THIS FIRST) ###\n"
            f"The following code is the current state of the active editor window:\n"
            f"```python\n{payload.context_code}\n```\n"
            f"### END OF CONTEXT ###\n\n"
            f"User Question: {payload.prompt}\n\n"
            f"Please use the code provided in the context above to answer the user's question."
        )

    try:
        response_text = await provider.generate_completion(
            prompt=final_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=1000,
        )

        # AI Self-Correction Loop is DISABLED here to avoid 500 errors on plain text explanations.
        sanitized_response = sanitize_ai_output(response_text)
        latency_ms = int((time.time() - start_time) * 1000)

        proposal_data = None
        try:
            match = re.search(r'(\{.*"proposal".*\})', response_text, re.DOTALL)
            if match:
                proposal_json = json.loads(match.group(1))
                p = proposal_json.get("proposal", {})
                proposal_data = {
                    "original_text": p.get("original", ""),
                    "proposed_text": p.get("proposed", ""),
                    "explanation": p.get("explanation", ""),
                }
        except Exception as e:
            log.debug("Failed to parse AI proposal JSON: %s", e)

        response = AIAssistantResponse(
            response=sanitized_response,
            provider=config.provider,
            model_used=config.model_name or provider.get_provider_name(),
            latency_ms=latency_ms,
            proposal=proposal_data
        )

        ai_request = AIAssistantRequest(
            project_id=project_id,
            user_id=user.id,
            prompt=payload.prompt,
            response=sanitized_response,
            provider=config.provider,
            model_used=config.model_name or provider.get_provider_name(),
            latency_ms=latency_ms,
            is_successful=True,
        )
        db.add(ai_request)
        await db.commit()

        await publish_project_event(
            project_id,
            {
                "type": "ai_assistant_response",
                "request_id": ai_request.id,
                "response": response_text,
                "provider": config.provider.value,
                "user_id": user.id,
            },
        )

        return response

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        log.error(f"AI assistant error for project {project_id}: {error_msg}")

        ai_request = AIAssistantRequest(
            project_id=project_id,
            user_id=user.id,
            prompt=payload.prompt,
            response="",
            provider=config.provider,
            model_used=config.model_name or provider.get_provider_name(),
            latency_ms=latency_ms,
            is_successful=False,
            error_message=error_msg,
        )
        db.add(ai_request)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI assistant error: {error_msg}",
        )


@router.get("/history", response_model=list[AIAssistantRequestOut])
async def get_assistant_history(
    project_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: int = 50,
) -> list[AIAssistantRequestOut]:
    """Get AI assistant request history for a project."""
    if not get_settings().ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Assistant is currently disabled",
        )
    await get_member(db, project_id, user.id)

    result = await db.execute(
        select(AIAssistantRequest)
        .where(AIAssistantRequest.project_id == project_id)
        .order_by(AIAssistantRequest.created_at.desc())
        .limit(limit)
    )
    requests = result.scalars().all()

    return [AIAssistantRequestOut.model_validate(req) for req in requests]
