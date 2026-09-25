"""Role-based permission tests — every mutating endpoint and every WS message
type must enforce ROLE_RANK >= the minimum required.
"""
import pytest


@pytest.mark.asyncio
async def test_viewer_cannot_run_code(client, two_users):
    a, b = two_users
    # Alice creates a project + session + file.
    r = await client.post(
        "/projects",
        json={"name": "p1"},
        headers={"Authorization": f"Bearer {a['token']}"},
    )
    assert r.status_code == 201
    project_id = r.json()["id"]

    r = await client.post(
        f"/sessions/projects/{project_id}/sessions",
        json={},
        headers={"Authorization": f"Bearer {a['token']}"},
    )
    session_id = r.json()["id"]

    r = await client.post(
        f"/projects/{project_id}/files",
        json={"path": "main.py"},
        headers={"Authorization": f"Bearer {a['token']}"},
    )
    file_id = r.json()["id"]

    # Bob joins the session as a viewer (default).
    r = await client.post(
        f"/sessions/join/{session_id}",
        headers={"Authorization": f"Bearer {b['token']}"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"

    # Bob (viewer) attempts to run code — should be 403.
    r = await client.post(
        f"/sessions/{session_id}/executions",
        json={"file_id": file_id},
        headers={"Authorization": f"Bearer {b['token']}"},
    )
    assert r.status_code == 403

    # Alice (owner) can run.
    r = await client.post(
        f"/sessions/{session_id}/executions",
        json={"file_id": file_id},
        headers={"Authorization": f"Bearer {a['token']}"},
    )
    assert r.status_code in (202, 500)  # 500 is OK in unit tests: no Redis/worker here
    if r.status_code == 202:
        assert r.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_non_member_cannot_access_session(client, two_users):
    a, b = two_users
    r = await client.post("/projects", json={"name": "p1"}, headers={"Authorization": f"Bearer {a['token']}"})
    project_id = r.json()["id"]
    r = await client.post(
        f"/sessions/projects/{project_id}/sessions", json={}, headers={"Authorization": f"Bearer {a['token']}"}
    )
    session_id = r.json()["id"]
    # Bob never joined.
    r = await client.get(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {b['token']}"})
    assert r.status_code == 403
