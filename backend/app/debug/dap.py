"""DAP (Debug Adapter Protocol) client wrapper.

Translates the protocol debugpy speaks over TCP into the small surface our
backend actually needs (set breakpoints, continue, step, get variables /
call stack). This is the Adapter pattern: we own the application-facing
shape and delegate the protocol details to this class.

Reference: https://microsoft.github.io/debug-adapter-protocol/
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager
from typing import Any

log = logging.getLogger(__name__)


class DapProtocolError(RuntimeError):
    pass


class DapClient:
    """Async TCP client for the Debug Adapter Protocol.

    debugpy, when started with `--wait-for-client`, accepts a single DAP
    client on the configured port. Multiple clients are not supported by
    debugpy itself, so this is single-driver by design.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5678) -> None:
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._seq = 1
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._event_handlers: dict[str, list] = {}
        self._connected = asyncio.Event()
        self._closed = False

    async def connect(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout if (time := __import__("time")) else None  # type: ignore[name-defined]
        while True:
            try:
                self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
                break
            except (ConnectionRefusedError, OSError):
                if deadline is not None and time.monotonic() > deadline:
                    raise
                await asyncio.sleep(0.2)
        self._connected.set()
        asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        self._closed = True
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    def on(self, event: str, handler) -> None:
        self._event_handlers.setdefault(event, []).append(handler)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while not self._closed:
                msg = await self._read_message()
                if msg is None:
                    return
                if "msg" not in msg:
                    continue
                if msg.get("type") == "response":
                    req_seq = msg.get("request_seq")
                    fut = self._pending.pop(req_seq, None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif msg.get("type") == "event":
                    event = msg.get("event")
                    for handler in self._event_handlers.get(event, []):
                        try:
                            handler(msg)
                        except Exception:  # noqa: BLE001
                            log.exception("event handler errored for %s", event)
        except Exception:  # noqa: BLE001
            log.exception("DAP read loop crashed")

    async def _read_message(self) -> dict | None:
        """Read one Content-Length framed DAP message."""
        assert self._reader is not None
        headers: dict[str, str] = {}
        while True:
            line = await self._reader.readline()
            if not line:
                return None
            line = line.decode("utf-8").rstrip("\r\n")
            if not line:
                break
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = await self._reader.readexactly(length)
        return json.loads(body)

    async def _send(self, payload: dict) -> None:
        assert self._writer is not None
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self._writer.write(header + body)
        await self._writer.drain()

    async def _request(self, command: str, arguments: dict | None = None) -> dict:
        await self._connected.wait()
        seq = self._seq
        self._seq += 1
        payload = {
            "seq": seq,
            "type": "request",
            "command": command,
            "arguments": arguments or {},
        }
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[seq] = fut
        await self._send(payload)
        response = await asyncio.wait_for(fut, timeout=60)
        if not response.get("success", False):
            raise DapProtocolError(f"DAP {command} failed: {response.get('message')}")
        return response

    # --- high-level operations our backend exposes ---

    async def initialize(self) -> None:
        await self._request("initialize", {"clientID": "concord", "adapterID": "debugpy"})

    async def launch(self, file_path: str) -> None:
        await self._request("launch", {"noDebug": False, "type": "python", "program": file_path})

    async def set_breakpoints(self, file_path: str, lines: list[int]) -> None:
        bps = [{"line": line} for line in lines]
        await self._request("setBreakpoints", {"source": {"path": file_path}, "breakpoints": bps})

    async def configuration_done(self) -> None:
        await self._request("configurationDone")

    async def continue_(self, thread_id: int) -> None:
        await self._request("continue", {"threadId": thread_id})

    async def next(self, thread_id: int) -> None:
        await self._request("next", {"threadId": thread_id})

    async def step_in(self, thread_id: int) -> None:
        await self._request("stepIn", {"threadId": thread_id})

    async def step_out(self, thread_id: int) -> None:
        await self._request("stepOut", {"threadId": thread_id})

    async def stack_trace(self, thread_id: int) -> list[dict]:
        resp = await self._request("stackTrace", {"threadId": thread_id, "startFrame": 0, "levels": 20})
        return resp.get("body", {}).get("stackFrames", [])

    async def scopes(self, frame_id: int) -> list[dict]:
        resp = await self._request("scopes", {"frameId": frame_id})
        return resp.get("body", {}).get("scopes", [])

    async def variables(self, variables_reference: int) -> list[dict]:
        resp = await self._request("variables", {"variablesReference": variables_reference})
        return resp.get("body", {}).get("variables", [])

    async def evaluate(self, expression: str, frame_id: int | None = None) -> Any:
        args: dict[str, Any] = {"expression": expression}
        if frame_id is not None:
            args["frameId"] = frame_id
        resp = await self._request("evaluate", args)
        return resp.get("body", {})


@asynccontextmanager
async def dap_session(host: str = "127.0.0.1", port: int = 5678):
    client = DapClient(host, port)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Synchronous check used by the worker to wait for debugpy to start listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
