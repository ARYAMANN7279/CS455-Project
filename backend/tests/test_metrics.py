"""Metrics authentication, project isolation and execution aggregates."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models import Execution, ExecutionEvent, ExecutionStatus, ProjectMember, Role, User

METRICS_ROUTES = (
    "/metrics/executions/summary",
    "/metrics/executions/last_hour",
    "/metrics/events/recent",
)


def _headers(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


@pytest.mark.asyncio
async def test_summary_on_empty_db_returns_zeros(
    client: AsyncClient, two_users: tuple[dict, dict]
) -> None:
    r = await client.get("/metrics/executions/summary", headers=_headers(two_users[0]))
    assert r.status_code == 200
    body = r.json()
    assert body["status_counts"] == {}
    assert body["avg_runtime_seconds"] == 0.0
    assert body["queue_wait_avg_seconds"] == 0.0
    assert body["queue_wait_p95_seconds"] == 0.0


@pytest.mark.asyncio
async def test_summary_computes_avg_runtime_and_queue_wait(
    db: AsyncSession, client: AsyncClient, project: dict
) -> None:
    now = datetime.now(UTC)

    # queue wait 2s, runtime 10s
    e1 = Execution(
        project_id=project["id"],
        file_id=project["file_id"],
        status=ExecutionStatus.COMPLETED,
        queued_at=now,
        started_at=now + timedelta(seconds=2),
        finished_at=now + timedelta(seconds=12),
    )
    # queue wait 4s, runtime 20s
    e2 = Execution(
        project_id=project["id"],
        file_id=project["file_id"],
        status=ExecutionStatus.COMPLETED,
        queued_at=now,
        started_at=now + timedelta(seconds=4),
        finished_at=now + timedelta(seconds=24),
    )
    db.add_all([e1, e2])
    await db.commit()

    r = await client.get("/metrics/executions/summary", headers=_headers(project["owner"]))
    assert r.status_code == 200
    body = r.json()

    assert body["status_counts"] == {"completed": 2}
    assert body["avg_runtime_seconds"] == pytest.approx(15.0, abs=0.01)
    assert body["queue_wait_avg_seconds"] == pytest.approx(3.0, abs=0.01)
    # p95 of [2, 4] via statistics.quantiles(n=100, method="inclusive") lands
    # very close to the max of a 2-sample set.
    assert body["queue_wait_p95_seconds"] == pytest.approx(4.0, abs=0.2)


@pytest.mark.asyncio
async def test_summary_excludes_executions_never_started(
    db: AsyncSession, client: AsyncClient, project: dict
) -> None:
    queued_only = Execution(
        project_id=project["id"],
        file_id=project["file_id"],
        status=ExecutionStatus.QUEUED,
    )
    db.add(queued_only)
    await db.commit()

    r = await client.get("/metrics/executions/summary", headers=_headers(project["owner"]))
    assert r.status_code == 200
    body = r.json()

    assert body["status_counts"] == {"queued": 1}
    assert body["queue_wait_avg_seconds"] == 0.0
    assert body["queue_wait_p95_seconds"] == 0.0


@pytest_asyncio.fixture
async def metrics_data(db: AsyncSession, client: AsyncClient, project: dict) -> dict:
    """Two visible projects and a newer, slower execution in an unrelated project."""
    projects = [project]
    for owner in (project["owner"], project["other"]):
        response = await client.post("/projects", json={"name": "metrics"}, headers=_headers(owner))
        assert response.status_code == 201
        project_id = response.json()["id"]
        response = await client.get(f"/projects/{project_id}/files", headers=_headers(owner))
        assert response.status_code == 200
        projects.append({"id": project_id, "file_id": response.json()[0]["id"]})

    now = datetime.now(UTC)
    executions = []
    for index, (target, runtime) in enumerate(zip(projects, (10, 20, 900), strict=True)):
        execution = Execution(
            project_id=target["id"],
            file_id=target["file_id"],
            status=ExecutionStatus.COMPLETED,
            queued_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=5) + timedelta(seconds=2 * (index + 1)),
            finished_at=now - timedelta(minutes=5) + timedelta(seconds=2 * (index + 1) + runtime),
        )
        db.add(execution)
        await db.flush()
        executions.append(execution)
        db.add(ExecutionEvent(execution_id=execution.id, event_type="completed", payload={}))

    old_execution = Execution(
        project_id=project["id"], file_id=project["file_id"], status=ExecutionStatus.QUEUED,
        queued_at=now - timedelta(hours=2),
    )
    db.add(old_execution)
    await db.flush()
    db.add(ExecutionEvent(execution_id=old_execution.id, event_type="queued", payload={}))
    await db.commit()
    return {
        "projects": projects,
        "visible_ids": {executions[0].id, executions[1].id, old_execution.id},
        "first_project_ids": {executions[0].id, old_execution.id},
        "latest_visible_id": old_execution.id,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("route", METRICS_ROUTES)
async def test_metrics_require_authentication(client: AsyncClient, route: str) -> None:
    response = await client.get(route)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", METRICS_ROUTES)
async def test_metrics_reject_invalid_tokens(client: AsyncClient, route: str) -> None:
    response = await client.get(route, headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_metrics_only_include_membership_projects(
    client: AsyncClient, project: dict, metrics_data: dict
) -> None:
    headers = _headers(project["owner"])
    response = await client.get(METRICS_ROUTES[0], headers=headers)
    assert response.status_code == 200
    summary = response.json()
    assert summary["status_counts"] == {"completed": 2, "queued": 1}
    assert summary["avg_runtime_seconds"] == 15.0
    assert summary["queue_wait_avg_seconds"] == 3.0
    assert summary["queue_wait_p95_seconds"] == pytest.approx(4.0, abs=0.2)
    response = await client.get(METRICS_ROUTES[1], headers=headers)
    assert response.status_code == 200
    assert response.json() == {"last_hour": 2}
    response = await client.get(METRICS_ROUTES[2], headers=headers)
    assert response.status_code == 200
    assert {event["execution_id"] for event in response.json()["events"]} == metrics_data["visible_ids"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", METRICS_ROUTES)
async def test_metrics_project_filter_narrows_member_results(
    client: AsyncClient, project: dict, metrics_data: dict, route: str
) -> None:
    response = await client.get(route, params={"project_id": project["id"]}, headers=_headers(project["owner"]))
    assert response.status_code == 200
    if route.endswith("summary"):
        assert response.json()["status_counts"] == {"completed": 1, "queued": 1}
        assert response.json()["avg_runtime_seconds"] == 10.0
        assert response.json()["queue_wait_avg_seconds"] == 2.0
    elif route.endswith("last_hour"):
        assert response.json() == {"last_hour": 1}
    else:
        assert {event["execution_id"] for event in response.json()["events"]} == metrics_data["first_project_ids"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", METRICS_ROUTES)
@pytest.mark.parametrize("unknown_project", [False, True])
async def test_metrics_project_filter_refuses_non_members(
    client: AsyncClient, project: dict, metrics_data: dict, route: str, unknown_project: bool
) -> None:
    project_id = 999999 if unknown_project else metrics_data["projects"][2]["id"]
    response = await client.get(route, params={"project_id": project_id}, headers=_headers(project["owner"]))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_recent_events_apply_membership_before_limit(
    client: AsyncClient, db: AsyncSession, project: dict, metrics_data: dict
) -> None:
    hidden_execution = Execution(
        project_id=metrics_data["projects"][2]["id"],
        file_id=metrics_data["projects"][2]["file_id"], status=ExecutionStatus.QUEUED,
    )
    db.add(hidden_execution)
    await db.flush()
    db.add(ExecutionEvent(execution_id=hidden_execution.id, event_type="private", payload={}))
    await db.commit()
    response = await client.get(METRICS_ROUTES[2], params={"limit": 1}, headers=_headers(project["owner"]))
    assert response.status_code == 200
    assert [event["execution_id"] for event in response.json()["events"]] == [metrics_data["latest_visible_id"]]


@pytest.mark.asyncio
async def test_viewer_can_read_metrics_for_their_project(
    client: AsyncClient, db: AsyncSession, project: dict, metrics_data: dict
) -> None:
    db.add(ProjectMember(project_id=project["id"], user_id=project["other"]["id"], role=Role.VIEWER))
    await db.commit()
    response = await client.get(METRICS_ROUTES[0], params={"project_id": project["id"]}, headers=_headers(project["other"]))
    assert response.status_code == 200
    assert response.json()["status_counts"] == {"completed": 1, "queued": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("route", METRICS_ROUTES)
async def test_user_without_memberships_gets_empty_metrics(
    client: AsyncClient, db: AsyncSession, metrics_data: dict, route: str
) -> None:
    user = User(username="outsider", email="outsider@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    response = await client.get(route, headers={"Authorization": f"Bearer {create_access_token(user.id)}"})
    assert response.status_code == 200
    if route.endswith("summary"):
        assert response.json() == {
            "status_counts": {}, "avg_runtime_seconds": 0.0,
            "queue_wait_avg_seconds": 0.0, "queue_wait_p95_seconds": 0.0,
        }
    elif route.endswith("last_hour"):
        assert response.json() == {"last_hour": 0}
    else:
        assert response.json() == {"events": []}
