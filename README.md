# Concord: Collaborative Code Execution Platform

> CS455 — Introduction to Software Engineering, IIT Kanpur (Fall 2026)  
> Instructor: Prof. Priyanka Bagade

Concord is a web platform where several users join a shared room and edit the same source file at the same time, with live cursors and presence. Any member can run the file in an isolated Docker sandbox, and the output goes to everyone in the session rather than only the person who started the run. The platform supports Python, C++, and JavaScript. An AI assistant sits beside the editor, answers questions about the open file, and can rewrite it in place.

Mental model: **VS Code Live Share + Replit + a debugger**, scoped to a course project.

---

## Architecture

```
client/          React + TypeScript frontend (Monaco editor, WebSocket client)
server/          FastAPI backend (REST API, WebSocket sync, CRDT, SQLAlchemy)
executor/        Sandboxed code-execution service (Docker-per-run)
```

Three subsystems:
1. **Real-time collaboration** — CRDT-based concurrent editing via Yjs, presence/cursors over WebSockets.
2. **Execution sandbox** — Language-specific Docker containers (Python, Node, GCC) per run, with limits on CPU/memory/time and no network access.
3. **App + persistence** — REST API for sessions and auth (JWT + bcrypt); PostgreSQL for storage; Redis for execution queuing and pub/sub.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Vite + Monaco Editor |
| Realtime | Yjs (CRDT) + y-monaco over WebSockets |
| Backend | FastAPI + SQLAlchemy + Alembic (Python) |
| Sandbox | Docker-per-run (`python:3.12-slim`, `node:22-slim`, `gcc:13`) |
| Database | PostgreSQL |
| Queue / PubSub | Redis |
| Infra | Docker Compose (Cloud VM + TLS reverse proxy) |
| CI/CD | GitHub Actions |

---

## User Roles

The role rank is `viewer < editor < owner`. Permissions are validated on every REST endpoint and incoming WebSocket message.

| Role | Permissions |
|---|---|
| **Viewer** | Join a session, read the document as it changes, see other members’ cursors/presence, view execution output, and ask the AI assistant questions. |
| **Editor** | Everything a viewer can do, plus edit the document, start and cancel runs, apply AI-generated code, and create/restore snapshots. |
| **Owner** | Everything an editor can do, plus create the session, add/remove members, change roles, and close the session. |

---

## Core Transactional Workflow (Execution)

Running code is modeled as a state machine:
`QUEUED → STARTING → RUNNING → [COMPLETED | FAILED | TIMEOUT | CANCELLED]`

1. An editor presses Run.
2. The backend reads the latest in-memory document, creates an `executions` row as `QUEUED`, and pushes a job to Redis.
3. A worker moves it through `STARTING` and `RUNNING`, then launches a language-specific container. (C++ compiles first).
4. The worker captures stdout, stderr, exit code, and elapsed time.
5. The final status and output are published on Redis and forwarded over WebSockets to all session members.

---

## AI Agent Integration

An AI agent runs in a panel to the right of the editor, scoped to one session and one file. It runs entirely on the backend to securely manage API keys, rate limits, and logging. 

**Tools provided to the agent:**
- `read_active_document`: Returns the current contents of the open file, so the agent works from what the user is looking at.
- `replace_active_document`: Writes a full replacement into the shared document.

---

## Getting started

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- pnpm (`npm i -g pnpm`)

### Run in development

```bash
# Start all infrastructure services (Postgres, Redis)
docker-compose up -d db redis

# Start the FastAPI backend
cd server
pip install -r requirements.txt
alembic upgrade head
fastapi dev main.py

# Start the React client
cd client
pnpm install
pnpm dev
```

---

## GenAI use log

_(Required by CS455 course policy — log all AI-assisted code here)_

| Date | File(s) | Tool | What was generated |
|------|---------|------|-------------------|
| | | | |

---

## Team (Group 9)

| Name | Roll No |
|------|---------|
| Pallav Rastogi | 230731 |
| Aamir Ahmad | 230010 |
| Aryamann Srivastava | 230211 |
| Tattwa Shivani | 231089 |
| Sanchit Arora | 230907 |
