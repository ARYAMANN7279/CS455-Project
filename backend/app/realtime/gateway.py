"""WebSocket gateway for collaborative editing.

Wire protocol (JSON over the WebSocket text channel, binary updates on a binary channel):

  client → server:
    {"op": "hello"}                    — initial connect, server sends full state back
    {"op": "sync_step1", "sv": "..."}  — client sends its state vector
    {"op": "awareness", "state": ...}  — cursor/presence
    {"op": "exec_event_ack", "id": N}  — client acknowledges an event id

  server → client (binary): a pycrdt state update

  server → client (text): JSON wrappers
    {"op": "full_state", "update_b64": "..."}     — sent on hello
    {"op": "exec_event", "event": {...}}           — forwarded from worker pub/sub
    {"op": "presence", "states": [...]}            — current awareness states
    {"op": "error", "message": "..."}              — e.g. permission denied

Edit propagation (binary frames) is the hot path. We serialize application of
updates under the room's lock so two near-simultaneous updates never interleave.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.deps import _bearer  # noqa: F401  (token decoded in the handler)
from app.core.security import decode_token
from app.db.session import AsyncSessionLocal
from app.models import File, Role, ProjectMember
from app.services.sandbox import sandbox
from app.realtime.crdt import (
    apply_update,
    diff_update,
    doc_from_bytes,
    doc_to_bytes,
    doc_to_text,
    new_doc,
    state_vector,
)
from app.realtime.execution_queue import publish_project_event, subscribe_project_events
from app.realtime.manager import room_manager, Connection
from app.debug.manager import DebugManager
from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

ws_router = APIRouter()


async def _resolve_member(db, project_id: int, user_id: int) -> ProjectMember | None:
    res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    )
    return res.scalar_one_or_none()


def _role_rank(role: str) -> int:
    return {"viewer": 0, "editor": 1, "debugger": 2, "owner": 3}.get(role, 0)


@ws_router.websocket("/ws/projects/{project_id}")
async def project_socket(ws: WebSocket, project_id: int, token: str = ""):
    """Project-level socket for structural updates (files/folders) and project-wide events."""
    await ws.accept()

    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (ValueError, KeyError):
        await ws.send_json({"op": "error", "message": "invalid token"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as db:
        member = await _resolve_member(db, project_id, user_id)
        if member is None:
            await ws.send_json({"op": "error", "message": "not a project member"})
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # Subscribe to execution events and structural updates for this project.
    conn = Connection(ws=ws, queue=asyncio.Queue())
    conn.writer_task = asyncio.create_task(room_manager._connection_writer(conn))
    room_manager._all_connections[ws] = conn
    room_manager.attach_to_project(project_id, ws)

    forwarder_task = asyncio.create_task(_forward_exec_events(
        conn,
        project_id
    ))

    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            # Project-level socket is primarily for receiving broadcasts, but we can handle heartbeats
            if "text" in message and message["text"] == "ping":
                await ws.send_text(json.dumps({"op": "pong"}))
    except Exception:
        log.exception("Project socket error")
    finally:
        forwarder_task.cancel()
        try:
            await forwarder_task
        except asyncio.CancelledError:
            pass

        room_manager.detach_from_project(project_id, ws)
        conn = room_manager._all_connections.pop(ws, None)
        if conn and conn.writer_task:
            conn.writer_task.cancel()

        log.info("Project socket disconnect user=%d project=%d", user_id, project_id)

@ws_router.websocket("/ws/projects/{project_id}/files/{file_id}")
async def collab_socket(ws: WebSocket, project_id: int, file_id: int, token: str = ""):
    """Collaborative editing socket. Token is passed as a query param because
    browsers can't set headers on the initial WebSocket upgrade."""
    await ws.accept()

    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (ValueError, KeyError):
        await ws.send_json({"op": "error", "message": "invalid token"})
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as db:
        member = await _resolve_member(db, project_id, user_id)
        if member is None:
            await ws.send_json({"op": "error", "message": "not a project member"})
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        file = await db.get(File, file_id)
        if not file:
            await ws.send_json({"op": "error", "message": "file not found"})
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # If the room doesn't exist yet AND the file has a checkpoint in the DB, hydrate
    # the doc from the latest version. This is how reconnect-after-server-restart works.
    room = room_manager.get_room(project_id, file_id)
    if room is None:
        room = await room_manager.get_or_create_room(project_id, file_id)
        async with AsyncSessionLocal() as db:
            from app.models import DocumentVersion

            res = await db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.file_id == file_id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
            latest = res.scalar_one_or_none()
            if latest:
                room.doc = doc_from_bytes(latest.snapshot_bytes)

    room = await room_manager.attach(project_id, file_id, ws, user_id, member)
    log.info("WS connect user=%d project=%d file=%d", user_id, project_id, file_id)

    # Subscribe to execution events for this session and forward as text messages.
    forwarder_task = asyncio.create_task(_forward_exec_events(room.connections[ws], project_id))

    try:
        # Send initial full state to the new client.
        room.connections[ws].send(doc_to_bytes(room.doc))

        last_activity = time.time()
        heartbeat = settings.websocket_heartbeat_interval

        while True:
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=heartbeat)
            except asyncio.TimeoutError:
                # Check if we've been silent for too long (2x heartbeat interval)
                if time.time() - last_activity > heartbeat * 2:
                    log.info("WS timeout: user %d silent for %ds, disconnecting", user_id, int(time.time() - last_activity))
                    break

                # Send a ping to check if client is still there
                try:
                    room.connections[ws].send(json.dumps({"op": "ping"}))
                except Exception:
                    break
                continue

            if message["type"] == "websocket.disconnect":
                break

            last_activity = time.time()

            if "bytes" in message and message["bytes"] is not None:
                # DISABLE binary frames to prevent double-application (we use Base64 JSON)
                log.debug("Ignoring binary update from user %d (use JSON)", user_id)
                continue

            if "text" in message and message["text"] is not None:
                try:
                    msg: dict[str, Any] = json.loads(message["text"])
                except json.JSONDecodeError:
                    room.connections[ws].send(json.dumps({"op": "error", "message": "invalid json"}))
                    continue

                op = msg.get("op")
                if op == "update":
                    # Handle Base64 encoded CRDT updates
                    # A viewer must never be able to mutate the document — the role
                    # rank is checked here, not only at connection time, matching the
                    # guarantee made for every REST endpoint and the debugger+ op below.
                    if _role_rank(member.role) < 1:  # editor+ required
                        room.connections[ws].send(json.dumps({"op": "error", "message": "editor role required to edit"}))
                        continue
                    try:
                        b64_data = msg.get("data", "")
                        update = base64.b64decode(b64_data)

                        # DEDUPLICATION: Prevent applying the same update twice
                        # pycrdt/yjs updates are idempotent, but applying them
                        # multiple times in some versions/configs can cause issues.
                        # We use the room lock to ensure atomic application.
                        async with room.lock:
                            apply_update(room.doc, update)

                        log.info("Applied update from user %d for room %d:%d. Size: %d bytes", user_id, room.project_id, room.file_id, len(update))
                        room_manager.broadcast(room, update, exclude=ws)
                    except Exception as e:
                        log.error("Error decoding Base64 update: %s", e)
                        room.connections[ws].send(json.dumps({"op": "error", "message": "invalid update format"}))
                    continue
                elif op == "awareness_update":
                    # Relay binary awareness update to other clients.
                    try:
                        b64_data = msg.get("data", "")
                        # Just relay the Base64 string as-is to other clients
                        relay_msg = json.dumps({"op": "awareness_update", "data": b64_data})
                        room_manager.broadcast(room, relay_msg, exclude=ws)
                    except Exception as e:
                        log.error("Error relaying awareness: %s", e)
                    continue
                elif op == "sync_step1":
                    remote_sv_b64 = msg.get("sv", "")
                    remote_sv = base64.b64decode(remote_sv_b64) if remote_sv_b64 else state_vector(room.doc)
                    async with room.lock:
                        diff = diff_update(room.doc, remote_sv)
                    room.connections[ws].send(diff)
                elif op == "awareness":
                    state = msg.get("state") or {}
                    state.setdefault("user_id", user_id)
                    state.setdefault("username", "anon")
                    _set_awareness(room, ws, state)
                    # Echo the change to *other* clients only. Sending the
                    # sender its own state back causes the well-known Yjs
                    # "cursor flicker" bug.
                    _broadcast_presence(room, exclude=ws)
                elif op == "debug":
                    log.info("DEBUG from client: %s", msg.get("message"))
                elif op == "ping":
                    room.connections[ws].send(json.dumps({"op": "pong"}))
                elif op == "pong":
                    continue
                elif op in ("continue", "next", "stepIn", "stepOut"):
                    # Handle debug operations - broadcast to all session members via DebugManager
                    # Check if debugger is enabled
                    if not settings.enable_debugger:
                        room.connections[ws].send(json.dumps({"op": "error", "message": "debugger is disabled"}))
                        continue
                    # Check debugger+ permission
                    if _role_rank(member.role) < 2:  # debugger+ requires role >= DEBUGGER (2)
                        room.connections[ws].send(json.dumps({"op": "error", "message": "debugger+ role required"}))
                        continue
                    user_id = int(payload["sub"])
                    await DebugManager.step(project_id, user_id, op)
                elif op == "assist_request":
                    # Handle AI assistant requests
                    # Check if AI assistant is globally enabled
                    if not settings.ai_assistant_enabled:
                        room.connections[ws].send(json.dumps({"op": "error", "message": "AI Assistant is currently disabled"}))
                        continue
                    # Check if user has permission to use AI assistant (all members per user request)
                    prompt = msg.get("prompt", "")
                    if not prompt:
                        room.connections[ws].send(json.dumps({"op": "error", "message": "prompt is required"}))
                        continue

                    # For now, we'll make a direct API call to the assistant endpoint
                    # In a more scalable implementation, this would go through a message queue
                    # or the application would make an internal API call
                    try:
                        # Import here to avoid circular imports
                        from app.api.assistant import request_assistant
                        from app.core.deps import DbSession
                        from app.models import User

                        # We need to get a database session and current user
                        # This is a simplified approach - in production, we might want
                        # to refactor this to use a service layer
                        async with AsyncSessionLocal() as db:
                            # Get the user from the token
                            token_user = await db.get(User, user_id)
                            if not token_user:
                                room.connections[ws].send(json.dumps({"op": "error", "message": "user not found"}))
                                continue

                            # Create a mock CurrentUser object
                            class MockCurrentUser:
                                def __init__(self, user):
                                    self.id = user.id

                            mock_user = MockCurrentUser(token_user)

                            # Import schemas
                            from app.schemas.assistant import AIAssistantRequestCreate

                            # Make the request
                            payload = AIAssistantRequestCreate(prompt=prompt)
                            response = await request_assistant(
                                project_id=project_id,
                                payload=payload,
                                user=mock_user,
                                db=db
                            )

                            # Send back the response
                            room.connections[ws].send(json.dumps({
                                "op": "assist_response",
                                "response": response.response,
                                "provider": response.provider,
                                "model_used": response.model_used,
                            }))
                    except Exception as e:
                        log.error(f"Error processing AI assistant request: {e}")
                        room.connections[ws].send(json.dumps({"op": "error", "message": "AI assistant temporarily unavailable"}))
                elif op == "assist_apply":
                    # Handle applying AI assistant response to the editor
                    # Check if AI assistant is globally enabled
                    if not settings.ai_assistant_enabled:
                        room.connections[ws].send(json.dumps({"op": "error", "message": "AI Assistant is currently disabled"}))
                        continue
                    # This would integrate with the CRDT to apply the changes
                    response_text = msg.get("response", "")
                    if not response_text:
                        room.connections[ws].send(json.dumps({"op": "error", "message": "response is required"}))
                        continue

                    # Validate the response before applying
                    try:
                        # Get file language from database
                        async with AsyncSessionLocal() as db:
                            file_obj = await db.get(File, file_id)
                            if not file_obj:
                                room.connections[ws].send(json.dumps({"op": "error", "message": "file not found"}))
                                continue
                            language = file_obj.language

                        # Validate using sandbox service
                        is_valid = await asyncio.get_event_loop().run_in_executor(
                            None, sandbox.validate_code, response_text, language
                        )
                        if not is_valid:
                            room.connections[ws].send(json.dumps({
                                "op": "error",
                                "message": f"Generated code is not valid {language} code"
                            }))
                            continue

                    except Exception as e:
                        log.error(f"Error validating AI assistant response: {e}")
                        room.connections[ws].send(json.dumps({"op": "error", "message": "Validation failed"}))
                        continue

                    # Apply the response as a CRDT update
                    # For simplicity, we'll treat the response as text to insert at the cursor
                    # In a real implementation, we'd want to be smarter about how we apply it
                    try:
                        # Create a doc from the response text
                        response_doc = new_doc(response_text)
                        response_update = doc_to_bytes(response_doc)


                        # Apply the update (this is a simplified approach)
                        # In reality, we'd want to integrate this at the current cursor position
                        async with room.lock:
                            apply_update(room.doc, response_update)

                        # Broadcast the update to all clients
                        room_manager.broadcast(room, response_update, exclude=ws)

                        # Confirm application
                        room.connections[ws].send(json.dumps({
                            "op": "assist_applied",
                            "message": "Response applied to editor"
                        }))
                    except Exception as e:
                        log.error(f"Error applying AI assistant response: {e}")
                        room.connections[ws].send(json.dumps({"op": "error", "message": "Failed to apply response"}))
                else:
                    room.connections[ws].send(json.dumps({"op": "error", "message": f"unknown op: {op}"}))

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("WS error")
    finally:
        room_manager.detach(room, ws)
        forwarder_task.cancel()
        try:
            await forwarder_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        log.info("WS disconnect user=%d project=%d file=%d", user_id, project_id, file_id)


def _set_awareness(room, ws, state: dict) -> None:
    """Store this connection's awareness state in the room's dict, keyed by
    the same uint32 client_id that yjs's awareness protocol uses."""
    from app.realtime.manager import _client_id_for  # avoid circular import

    cid = _client_id_for(ws)
    room.awareness[cid] = {**state, "client_id": cid}


def _broadcast_presence(room, exclude=None) -> None:
    """Send the current room awareness snapshot to other clients.

    ``exclude`` is the WebSocket of the sender (we don't echo presence back to
    the originator — that's the cursor-flicker bug).
    """
    # Build a list of (client_id, state) tuples; the frontend's
    # y-protocols/awareness layer expects the client_id inside each state.
    states = [
        {**state, "client_id": cid}
        for cid, state in room.awareness.items()
    ]
    msg = json.dumps({"op": "presence", "states": states})
    room_manager.broadcast(room, msg, exclude=exclude)


async def _forward_exec_events(conn: Connection, project_id: int) -> None:
    """Forward worker → project events (stdout, status changes) to the WS client."""
    log.info("Starting execution event forwarder for project %d", project_id)
    try:
        async for data in subscribe_project_events(project_id):
            try:
                log.info("Forwarding exec event to project %d: %s", project_id, data)
                conn.send(
                    json.dumps({"op": "exec_event", "event": json.loads(data)})
                )
            except Exception:  # noqa: BLE001
                log.exception("Error sending exec event to WS")
                return
    except asyncio.CancelledError:
        log.info("Execution event forwarder cancelled for project %d", project_id)
        return
    except Exception:  # noqa: BLE001
        log.exception("forwarder crashed for project %d", project_id)
