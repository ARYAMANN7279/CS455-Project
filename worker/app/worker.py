import asyncio
import json
import logging
import os
import socket
import time
import tempfile
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis_async
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import (
    Base,
    Execution,
    ExecutionStatus,
    File,
    DocumentVersion,
    DebugSession,
    Breakpoint,
)
from app.realtime.execution_queue import (
    QUEUE_NAME,
    CANCEL_CHANNEL_PREFIX,
    publish_project_event,
)
from app.realtime.crdt import doc_from_bytes, doc_to_text
from app.debug import debug_manager
from app.services.sandbox import sandbox, RunResult
from docker.errors import APIError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

async def _transition(execution_id: int, status: ExecutionStatus, **kwargs) -> None:
    """Update execution status and metadata in DB."""
    async with AsyncSessionLocal() as db:
        execution = await db.get(Execution, execution_id)
        if execution:
            execution.status = status
            for k, v in kwargs.items():
                setattr(execution, k, v)
            await db.commit()

async def _publish_status(project_id: int, execution_id: int, status: str) -> None:
    """Broadcast status update to the project."""
    await publish_project_event(project_id, {
        "type": "execution_status",
        "execution_id": execution_id,
        "status": status,
    })

async def _mount_workspace(project_id: int, main_file_id: int, tmpdir: str) -> None:
    """Fetch all files in the project and recreate the folder structure in tmpdir."""
    async with AsyncSessionLocal() as db:
        # 1. Fetch all files for the project
        res = await db.execute(select(File).where(File.project_id == project_id))
        project_files = res.scalars().all()

        # 2. For each file, find the latest version/snapshot
        for file in project_files:
            v_res = await db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.file_id == file.id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
            latest = v_res.scalar_one_or_none()

            content = ""
            if latest:
                content = doc_to_text(doc_from_bytes(latest.snapshot_bytes))

            # 3. Create directory and write file
            full_path = os.path.join(tmpdir, file.path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

async def _run_one(payload: dict) -> None:
    execution_id = int(payload["execution_id"])
    project_id = int(payload["project_id"])
    file_id = int(payload["file_id"])
    source_text = payload.get("source_text", "")
    debug = payload.get("debug", False)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"

    language = payload.get("language", "python")

    log.info("worker=%s picked up execution=%d (debug=%s)", worker_id, execution_id, debug)

    now = datetime.now(timezone.utc)
    await _transition(
        execution_id,
        ExecutionStatus.STARTING,
        worker_id=worker_id,
        started_at=now,
    )
    await _publish_status(project_id, execution_id, "starting")

    try:
        cancel_event = asyncio.Event()
        cancel_sub = None
        listener = None
        try:
            cancel_sub = aioredis_async.from_url(get_settings().redis_url, decode_responses=False)
            pubsub = cancel_sub.pubsub()
            await pubsub.subscribe(CANCEL_CHANNEL_PREFIX + str(execution_id))

            async def _listen_cancel() -> None:
                try:
                    async for msg in pubsub.listen():
                        if msg.get("type") == "message":
                            cancel_event.set()
                            return
                except Exception:
                    log.warning("cancel listener crashed", exc_info=True)

            listener = asyncio.create_task(_listen_cancel())
        except Exception:
            cancel_sub = None
            listener = None

        from app.runtime.registry import get_runtime_config
        try:
            runtime_config = get_runtime_config(language)
        except ValueError:
            runtime_config = get_runtime_config("python")

        with tempfile.TemporaryDirectory(prefix="concord-exec-") as tmpdir:
            try:
                await _mount_workspace(project_id, file_id, tmpdir)
            except Exception as e:
                log.error("Failed to mount workspace for project %d: %s", project_id, e)
                raise e

            async with AsyncSessionLocal() as db:
                file_obj = await db.get(File, file_id)
                if not file_obj:
                    raise Exception("Main file not found in DB")
                main_path_rel = file_obj.path

            file_name = os.path.basename(main_path_rel)
            main_path = os.path.join(tmpdir, main_path_rel)

            if source_text:
                with open(main_path, "w", encoding="utf-8") as f:
                    f.write(source_text)

                # Also write to the runtime's expected 'main' file for building/running
                from app.runtime.registry import RUNTIMES, Language
                try:
                    lang_enum = Language(language)
                    runtime_config = RUNTIMES[lang_enum]
                    main_runtime_path = os.path.join(tmpdir, f"main{runtime_config.file_extension}")
                    with open(main_runtime_path, "w", encoding="utf-8") as f:
                        f.write(source_text)
                except Exception:
                    pass

            if runtime_config.build_command:
                await _transition(execution_id, ExecutionStatus.COMPILING)
                await _publish_status(project_id, execution_id, "compiling")
                try:
                    await asyncio.to_thread(
                        sandbox.build, runtime_config.image, tmpdir, runtime_config.build_command, runtime_config.build_workdir
                    )
                except Exception as e:
                    log.error("Build failed for execution %d: %s", execution_id, e)
                    raise e

            await _transition(execution_id, ExecutionStatus.RUNNING)
            await _publish_status(project_id, execution_id, "running")

            result_holder: dict[str, RunResult | None] = {"result": None}
            error_holder: dict[str, BaseException | None] = {"error": None}

            def _run_in_thread() -> None:
                try:
                    if debug:
                        settings = get_settings()
                        timeout = settings.sandbox_timeout_seconds

                        if runtime_config.debug_config:
                            entrypoint = runtime_config.debug_config["entrypoint"]
                            ports = runtime_config.debug_config.get("ports")
                        else:
                            entrypoint = runtime_config.entrypoint
                            ports = None

                        debug_session_info = payload.get("debug_session_info")
                        file_path = f"/workspace/{main_path_rel}"
                        breakpoints = []
                        if debug_session_info:
                            file_path = debug_session_info.get("file_path", f"/workspace/{main_path_rel}")
                            breakpoints = debug_session_info.get("breakpoints", [])

                        started = time.monotonic()
                        try:
                            container = sandbox.client.containers.run(
                                image=runtime_config.image,
                                command=entrypoint,
                                network_disabled=(settings.sandbox_network == "none"),
                                mem_limit=settings.sandbox_mem_limit,
                                cpu_quota=settings.sandbox_cpu_quota,
                                pids_limit=settings.sandbox_pids_limit,
                                read_only=True,
                                user="runner",
                                working_dir="/workspace",
                                volumes={tmpdir: {"bind": "/workspace", "mode": "ro"}},
                                ports=ports,
                                detach=True,
                                remove=False,
                                stdout=True,
                                stderr=True,
                            )

                            if debug_manager is not None:
                                try:
                                    time.sleep(0.5)
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        loop.run_until_complete(
                                            debug_manager.start(
                                                session_id=project_id,
                                                host="localhost",
                                                port=5678 if language == "python" else 9229,
                                                file_path=file_path,
                                                breakpoints=breakpoints
                                            )
                                        )
                                    except Exception:
                                        pass
                                    finally:
                                        loop.close()
                                except Exception as e:
                                    log.warning("Failed to start debug manager: %s", e)

                            try:
                                result_wait = container.wait(timeout=timeout)
                                exit_code = int(result_wait.get("StatusCode", 1))
                            except Exception:
                                try:
                                    container.kill()
                                except APIError:
                                    log.warning("kill after timeout failed", exc_info=True)
                                try:
                                    result_wait = container.wait(timeout=2)
                                    exit_code = int(result_wait.get("StatusCode", 137))
                                except Exception:
                                    exit_code = 124

                            stdout_bytes = b""
                            stderr_bytes = b""
                            try:
                                stdout_bytes = container.logs(stdout=True, stderr=False)
                                stderr_bytes = container.logs(stdout=False, stderr=True)
                            except APIError:
                                log.warning("log capture failed", exc_info=True)

                            duration = time.monotonic() - started
                            try:
                                container.remove(force=True)
                            except APIError:
                                pass

                            result = RunResult(
                                exit_code=exit_code,
                                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                                timed_out=(exit_code == 124),
                                duration_seconds=duration,
                            )
                        except Exception as e:
                            raise e
                    else:
                        result = sandbox.run(
                            code=source_text,
                            language=language,
                            timeout_seconds=get_settings().sandbox_timeout_seconds,
                            debug=debug,
                            workspace_dir=tmpdir,
                        )

                        result_holder["result"] = result
                except Exception as e:
                    error_holder["error"] = e

            runner_task = asyncio.create_task(asyncio.to_thread(_run_in_thread))
            cancel_wait = asyncio.create_task(cancel_event.wait())
            done, pending = await asyncio.wait(
                {runner_task, cancel_wait}, return_when=asyncio.FIRST_COMPLETED
            )

            cancelled = False
            if cancel_wait in done:
                cancelled = True
                runner_task.cancel()
                try:
                    await runner_task
                except (asyncio.CancelledError, Exception):
                    pass

            if runner_task in done:
                try:
                    await runner_task
                except Exception:
                    log.exception("runner task errored")

            if listener is not None:
                listener.cancel()
                try:
                    await listener
                except (asyncio.CancelledError, Exception):
                    pass
            if cancel_sub is not None:
                try:
                    await cancel_sub.close()
                except Exception:
                    pass

            if cancelled:
                await _transition(
                    execution_id,
                    ExecutionStatus.CANCELLED,
                    finished_at=datetime.now(timezone.utc),
                )
                await _publish_status(project_id, execution_id, "cancelled")
                return

            if error_holder["error"] is not None:
                await _transition(
                    execution_id,
                    ExecutionStatus.FAILED,
                    stderr=str(error_holder["error"]),
                    finished_at=datetime.now(timezone.utc),
                )
                await _publish_status(project_id, execution_id, "failed")
                return

            result = result_holder["result"]
            assert result is not None
            timed_out = result.timed_out
            target = ExecutionStatus.TIMEOUT if timed_out else (
                ExecutionStatus.COMPLETED if result.exit_code == 0 else ExecutionStatus.FAILED
            )

            await _transition(
                execution_id,
                target,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                finished_at=datetime.now(timezone.utc),
            )
            await publish_project_event(
                project_id,
                {
                    "type": "execution_output",
                    "execution_id": execution_id,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "duration": result.duration_seconds,
                },
            )
            await _publish_status(project_id, execution_id, target.value)

    except Exception as e:
        log.error("Unexpected error during execution %d: %s", execution_id, e, exc_info=True)
        await _transition(
            execution_id,
            ExecutionStatus.FAILED,
            stderr=f"Internal worker error: {e}",
            finished_at=datetime.now(timezone.utc),
        )
        await _publish_status(project_id, execution_id, "failed")
    finally:
        if listener:
            listener.cancel()
        if cancel_sub:
            await cancel_sub.close()

async def main():
    log.info("Starting execution worker...")
    r = aioredis_async.from_url(get_settings().redis_url, decode_responses=True)

    while True:
        try:
            res = await r.brpop(QUEUE_NAME, timeout=0)
            if res:
                _, payload_json = res
                payload = json.loads(payload_json)
                await _run_one(payload)
        except Exception as e:
            log.exception("Worker loop error: %s", e)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
