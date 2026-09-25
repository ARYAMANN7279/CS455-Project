# Concord — API Specification

All REST endpoints accept and return JSON. Auth is via `Authorization: Bearer <token>`.

## Auth

### `POST /auth/signup`
Body: `{username, email, password}` → 201 `{access_token, user}`

### `POST /auth/login`
Body: `{username, password}` → 200 `{access_token, user}`

## Projects

### `POST /projects`
Body: `{name}` → 201 `Project`

### `GET /projects` → `[Project]`

## Sessions

### `POST /sessions/projects/{project_id}/sessions` → 201 `Session`

### `POST /sessions/join/{session_id}` → `{session, role}`

### `GET /sessions/{session_id}` → `Session`

### `GET /sessions/{session_id}/members` → `[SessionMember]`

### `POST /sessions/{session_id}/members/{user_id}` (owner only) → `SessionMember`
Body: `{role: "viewer"|"editor"|"debugger"|"owner"}`

### `PATCH /sessions/{session_id}/members/{user_id}` (owner only) → `SessionMember`

### `DELETE /sessions/{session_id}/members/{user_id}` → 204

## Files

### `POST /projects/{project_id}/files` → 201 `File`
Body: `{path}`

### `GET /projects/{project_id}/files` → `[File]`

### `GET /projects/{project_id}/files/{file_id}/content` → `{file_id, text, version}`

## Executions

### `POST /sessions/{session_id}/executions` (editor+) → 202 `Execution`
Body: `{file_id}`

### `GET /sessions/{session_id}/executions` → `[Execution]`

### `GET /sessions/{session_id}/executions/{id}` → `Execution`

### `POST /sessions/{session_id}/executions/{id}/cancel` (editor+) → `Execution`

## Snapshots

### `POST /sessions/{session_id}/snapshots` (editor+) → 201 `Snapshot`
Body: `{label}`

### `GET /sessions/{session_id}/snapshots` → `[Snapshot]`

### `POST /sessions/{session_id}/snapshots/{id}/restore` (editor+) → 202 `{restored_files: int}`

## Breakpoints

### `GET /sessions/{session_id}/breakpoints?file_id=N` → `[Breakpoint]`

### `PUT /sessions/{session_id}/breakpoints` (debugger+) → `[Breakpoint]`
Body: `[{file_id, line, enabled}]`

## Debug

### `POST /sessions/{session_id}/debug/start?file_id=N` (debugger+) → `{status: "requested"}`

## Metrics

### `GET /metrics/executions/summary` → `{status_counts, avg_runtime_seconds}`

### `GET /metrics/executions/last_hour` → `{last_hour: int}`

### `GET /metrics/events/recent?limit=N` → `{events: [...]}`

## WebSocket

### `ws://host/ws/sessions/{session_id}/files/{file_id}?token=<jwt>`

Frames:

| Type | Direction | Purpose |
|---|---|---|
| binary | client → server | CRDT update (Yjs update bytes) |
| binary | server → client | Broadcast update (re-applied to local Y.Doc) |
| text | client → server | `{"op":"hello"}` — full state sent back as binary |
| text | client → server | `{"op":"sync_step1","sv":"<base64>"}` — state vector for re-sync |
| text | client → server | `{"op":"awareness","state":{...}}` — cursor / presence |
| text | client → server | `{"op":"ping"}` — keep-alive |
| text | server → client | `{"op":"exec_event","event":{...}}` — execution status / output / debug state |
| text | server → client | `{"op":"presence","states":[...]}` |
| text | server → client | `{"op":"error","message":"..."}` |
| text | server → client | `{"op":"pong"}` |

## Error model

All REST errors return:
```json
{ "detail": "human-readable reason" }
```

Standard codes used: 400 (validation), 401 (unauth), 403 (forbidden / wrong role), 404 (not found), 409 (conflict), 500 (server error).
