"""Debug Manager — owns the DAP session for a single active debug run.

The single-driver model: only one user controls the debugger at a time. The
manager tracks who that user is. When a `stopped` event arrives from debugpy,
the manager fans the resulting state (paused line, call stack, variables) out
to every session member over the WS gateway.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.debug.dap import DapClient, port_open
from app.realtime.execution_queue import publish_project_event
from app.core.config import get_settings

log = logging.getLogger(__name__)

settings = get_settings()


class DebugManager:
    def __init__(self) -> None:
        # session_id -> DebugSessionState
        self._sessions: dict[int, "DebugSessionState"] = {}

    async def start(self, session_id: int, host: str, port: int, file_path: str, breakpoints: list[int]) -> None:
        # Wait for the sandbox-side debugpy to start listening.
        for _ in range(150):  # ~15s
            if port_open(host, port):
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("debugpy did not start in time")

        client = DapClient(host, port)
        await client.connect()
        await client.initialize()
        await client.launch(file_path)
        await client.set_breakpoints(file_path, breakpoints)
        await client.configuration_done()

        state = DebugSessionState(session_id=session_id, client=client, driver_user_id=None)
        self._sessions[session_id] = state

        client.on("stopped", lambda msg: asyncio.create_task(self._on_stopped(session_id, msg)))
        client.on("continued", lambda msg: asyncio.create_task(self._on_continued(session_id, msg)))
        client.on("exited", lambda msg: asyncio.create_task(self._on_exited(session_id, msg)))
        client.on("terminated", lambda msg: asyncio.create_task(self._on_exited(session_id, msg)))

    async def set_breakpoints(self, session_id: int, file_path: str, lines: list[int]) -> None:
        state = self._sessions.get(session_id)
        if state is None:
            return
        await state.client.set_breakpoints(file_path, lines)

    async def step(self, session_id: int, user_id: int, command: str) -> None:
        state = self._sessions.get(session_id)
        if state is None or state.paused_thread is None:
            return
        # Enforce single-driver: the first user to step becomes the driver for
        # the lifetime of this debug session. Other users can observe the
        # debugger state via debug_paused / debug_running session events but
        # cannot drive it. To take over, the current driver must disconnect
        # or the debug session must be restarted.
        if state.driver_user_id is None:
            state.driver_user_id = user_id
        elif state.driver_user_id != user_id:
            log.info(
                "step rejected: user=%d is not the driver (driver=%d) for session=%d",
                user_id, state.driver_user_id, session_id,
            )
            return
        tid = state.paused_thread
        if command == "continue":
            await state.client.continue_(tid)
        elif command == "next":
            await state.client.next(tid)
        elif command == "stepIn":
            await state.client.step_in(tid)
        elif command == "stepOut":
            await state.client.step_out(tid)

    async def fetch_frame(self, session_id: int, frame_index: int = 0) -> dict:
        state = self._sessions.get(session_id)
        if state is None or state.paused_thread is None:
            return {}
        stack = await state.client.stack_trace(state.paused_thread)
        if not stack:
            return {}
        frame = stack[min(frame_index, len(stack) - 1)]
        scopes = await state.client.scopes(frame["id"])
        variables: list[dict] = []
        for sc in scopes:
            try:
                variables.extend(await state.client.variables(sc["variablesReference"]))
            except Exception:  # noqa: BLE001
                continue
        return {
            "frame": {
                "name": frame.get("name"),
                "line": frame.get("line"),
                "source": (frame.get("source") or {}).get("path"),
            },
            "scopes": [{"name": s["name"], "variablesReference": s["variablesReference"]} for s in scopes],
            "variables": variables,
            "stack": [
                {"name": f.get("name"), "line": f.get("line"), "id": f["id"]} for f in stack
            ],
        }

    async def stop(self, session_id: int) -> None:
        state = self._sessions.pop(session_id, None)
        if state is None:
            return
        await state.client.close()

    # --- DAP event fanout ---

    async def _on_stopped(self, session_id: int, msg: dict) -> None:
        body = msg.get("body", {}) or {}
        thread_id = body.get("threadId")
        state = self._sessions.get(session_id)
        if state is None:
            return
        state.paused_thread = thread_id
        details = await self.fetch_frame(session_id, 0)
        await publish_project_event(
            session_id,
            {
                "type": "debug_paused",
                "thread_id": thread_id,
                "reason": body.get("reason"),
                **details,
            },
        )

    async def _on_continued(self, session_id: int, _msg: dict) -> None:
        state = self._sessions.get(session_id)
        if state:
            state.paused_thread = None
        await publish_project_event(session_id, {"type": "debug_running"})

    async def _on_exited(self, session_id: int, _msg: dict) -> None:
        state = self._sessions.pop(session_id, None)
        if state:
            await state.client.close()
        await publish_project_event(session_id, {"type": "debug_stopped"})


class DebugSessionState:
    __slots__ = ("session_id", "client", "driver_user_id", "paused_thread")

    def __init__(self, session_id: int, client: DapClient, driver_user_id: int | None) -> None:
        self.session_id = session_id
        self.client = client
        self.driver_user_id = driver_user_id
        self.paused_thread: int | None = None


# Singleton debug manager - None if debugger is disabled
debug_manager = DebugManager() if settings.enable_debugger else None
