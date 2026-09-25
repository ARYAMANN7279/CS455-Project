"""Breakpoint CRUD round-trip."""
import pytest


@pytest.mark.asyncio
async def test_breakpoint_upsert_and_replace(client, two_users):
    a, _ = two_users
    h = {"Authorization": f"Bearer {a['token']}"}
    r = await client.post("/projects", json={"name": "p1"}, headers=h)
    project_id = r.json()["id"]
    r = await client.post(
        f"/sessions/projects/{project_id}/sessions", json={}, headers=h
    )
    session_id = r.json()["id"]
    r = await client.post(
        f"/projects/{project_id}/files", json={"path": "main.py"}, headers=h
    )
    file_id = r.json()["id"]

    r = await client.put(
        f"/sessions/{session_id}/breakpoints",
        json=[{"file_id": file_id, "line": 1, "enabled": True}],
        headers=h,
    )
    assert r.status_code == 200
    r = await client.put(
        f"/sessions/{session_id}/breakpoints",
        json=[{"file_id": file_id, "line": 7, "enabled": True}],
        headers=h,
    )
    assert r.status_code == 200
    r = await client.get(f"/sessions/{session_id}/breakpoints?file_id={file_id}", headers=h)
    assert r.status_code == 200
    lines = sorted(b["line"] for b in r.json())
    assert lines == [7]


@pytest.mark.asyncio
async def test_viewer_cannot_set_breakpoints(client, two_users):
    a, b = two_users
    h = {"Authorization": f"Bearer {a['token']}"}
    r = await client.post("/projects", json={"name": "p1"}, headers=h)
    project_id = r.json()["id"]
    r = await client.post(
        f"/sessions/projects/{project_id}/sessions", json={}, headers=h
    )
    session_id = r.json()["id"]
    r = await client.post(
        f"/projects/{project_id}/files", json={"path": "main.py"}, headers=h
    )
    file_id = r.json()["id"]
    # Bob joins as viewer.
    await client.post(f"/sessions/join/{session_id}", headers={"Authorization": f"Bearer {b['token']}"})

    r = await client.put(
        f"/sessions/{session_id}/breakpoints",
        json=[{"file_id": file_id, "line": 3, "enabled": True}],
        headers={"Authorization": f"Bearer {b['token']}"},
    )
    assert r.status_code == 403
