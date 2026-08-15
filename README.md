# Collaborative Code Execution & Debugging Platform

> CS455 — Introduction to Software Engineering, IIT Kanpur (Fall 2026)  
> Instructor: Prof. Priyanka Bagade

A web platform where multiple users join a shared room, edit the same code in real time (live cursors + presence), execute it in a sandboxed environment, and debug it collaboratively.

Mental model: **VS Code Live Share + Replit + a debugger**, scoped to a course project.

---

## Architecture

```
client/          React + TypeScript frontend (Monaco editor, WebSocket client)
server/          Node.js + TypeScript backend (REST API, WebSocket sync, CRDT)
executor/        Sandboxed code-execution service (Docker-per-run)
```

Three subsystems:
1. **Real-time collaboration** — CRDT-based concurrent editing, presence/cursors via WebSocket
2. **Execution sandbox** — Docker container per run, CPU/memory/time limits, no network
3. **App + persistence** — auth, rooms, documents; Postgres; optional Redis pub/sub

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Vite + Monaco Editor |
| Realtime | Yjs (CRDT) + y-websocket |
| Backend | Node.js + TypeScript + Express |
| Sandbox | Docker-per-run (Python initially) |
| Database | Postgres |
| Infra | Docker Compose |
| CI/CD | GitHub Actions |
| Static analysis | ESLint + TypeScript strict |

---

## Getting started

### Prerequisites
- Node.js 20+
- Docker + Docker Compose
- pnpm (`npm i -g pnpm`)

### Run in development

```bash
# Install all dependencies
pnpm install

# Start all services (server + client + db)
docker-compose up -d db
pnpm --filter server dev &
pnpm --filter client dev
```

Server runs on `http://localhost:3001`, client on `http://localhost:5173`.

---

## Project structure

```
.
├── client/                 # React frontend
│   └── src/
│       ├── components/     # Editor, Room, Output panels
│       ├── hooks/          # useRoom, usePresence, useExecution
│       └── lib/            # CRDT binding, WS client
├── server/                 # Node.js backend
│   └── src/
│       ├── routes/         # REST: auth, rooms
│       ├── ws/             # WebSocket: sync, presence
│       └── db/             # Postgres schema + queries
├── executor/               # Sandbox execution service
│   └── Dockerfile
├── .github/workflows/      # CI pipeline
└── docker-compose.yml
```

---

## GenAI use log

_(Required by CS455 course policy — log all AI-assisted code here)_

| Date | File(s) | Tool | What was generated |
|------|---------|------|-------------------|
| | | | |

---

## Team

| Name | Roll No |
|------|---------|
| Aryamann Srivastava | 230211 |
| Aamir Ahmad | 230010 |
| Pallav Rastogi | 230731 |
| Tattwa Shivani | 231089 |
| Sanchit Arora | 230907 |
