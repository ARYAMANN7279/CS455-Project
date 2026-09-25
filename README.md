# Concord — Collaborative Code Execution & Debugging Platform

Concord is a high-performance, cloud-native collaboration platform designed for real-time software development. It is not just a code editor; it is a distributed execution engine that enables teams to write, run, and debug code together in a secure, synchronized environment.

## 🚀 Getting Started

### Prerequisites
- **Docker & Docker Compose** (Required for all services)
- **Node.js 20+** (For local frontend development)
- **Python 3.12** (For local backend development)

### Local Installation & Setup

1. **Clone the Project**
   ```bash
   git clone https://github.com/your-repo/concord.git
   cd concord
   ```

2. **Environment Configuration**
   ```bash
   cp .env.example .env
   # Edit .env if you need to change database credentials or API keys
   ```

3. **Launch the Application**
   Start all services (Postgres, Redis, backend, worker, frontend) in the background:
   ```bash
   docker compose up -d
   ```

4. **Access the App**
   - **Frontend:** [http://localhost:5173](http://localhost:5173)
   - **API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🌟 Core Capabilities

### 🤝 Real-Time Collaboration (CRDTs)
Unlike traditional editors that rely on simple locking or frequent polling, Concord uses **Conflict-free Replicated Data Types (CRDTs)** via **Yjs** and **pycrdt**.
- **Zero-Latency Editing**: Multiple users edit the same file simultaneously with seamless convergence.
- **Presence Awareness**: Real-time tracking of user cursors and active collaborators.

### 🛡️ Secure Distributed Execution
Code is never executed on the host server. Instead, Concord employs a **distributed sandbox architecture**:
- **Isolated Sandboxes**: Every "Run" command triggers the creation of a fresh, isolated Docker container.
- **Hardened Security**: Containers are launched with `network none`, strict memory limits, and PID limits to prevent host compromise.
- **Asynchronous Pipeline**: Uses **Redis and RQ (Redis Queue)** to manage execution requests across a scalable worker pool.

### 🐞 Collaborative Debugging
Concord implements the **Debug Adapter Protocol (DAP)** to bring a professional debugging experience to the browser:
- **Remote Debugging**: Integrates `debugpy` inside the sandbox to allow deep inspection of running code.
- **Single-Driver, Broadcast-Watch**: One user controls the debugging session (stepping, breakpoints), while all other members see the execution state update live on their screens.

### 🔑 Enterprise-Grade Access Control
A robust **Role-Based Access Control (RBAC)** system ensures project security:
- **Granular Roles**: `viewer`, `editor`, `debugger`, and `owner` roles define specific permissions.
- **Join Workflow**: A formal "Request Access $\rightarrow$ Approve/Reject" flow for secure project membership.

---

## 🤖 Developing with AI Agents

Concord is designed to be extended using AI agents (like Claude Code).

### Agent Workflows
- **Feature Implementation**: Request the agent to "implement a new API endpoint" or "add a UI component".
- **Automated Debugging**: Provide error logs and ask the agent to "diagnose and fix the crash".
- **Architecture Refactoring**: Ask the agent to "optimize the member management logic" or "improve the execution pipeline".

---

## 🛠 Architecture Overview

- **Frontend**: React + TypeScript + Monaco Editor + Yjs.
- **Backend**: FastAPI + SQLAlchemy + Alembic + JWT.
- **Collab Gateway**: `pycrdt` over WebSockets for state synchronization.
- **Execution**: Redis + RQ $\rightarrow$ Isolated Docker Containers.
- **Debugger**: `debugpy` $\rightarrow$ DAP $\rightarrow$ WebSocket Adapter.
- **Database**: PostgreSQL (Authoritative store for users, permissions, and snapshots).

---

## 🧪 Testing

```bash
# Run backend unit and integration tests
docker compose exec backend pytest

# Run concurrency and convergence tests (10+ clients)
docker compose exec backend pytest tests/test_concurrent_edits.py

# Run worker-specific unit tests
docker compose exec worker pytest worker/tests/
```

## 📈 Project Phases
Detailed technical specs can be found in the `docs/` directory:
- `docs/build-spec.md` (Build order)
- `docs/requirements.md` (Functional requirements)
- `docs/database.md` (Schema design)
- `docs/api.md` (API specifications)
