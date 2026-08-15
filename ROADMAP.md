# CS455 Project Roadmap — Collaborative Code Execution & Debugging Platform

> **What this document is:** a shared-understanding + planning reference for the team, mapped to
> Prof. Priyanka Bagade's software-development lifecycle (Lecture 1) and the "What is in CS455?"
> grading priorities. It is **not** a graded deliverable and should not be pasted into one.
>
> **Course:** CS455 Introduction to Software Engineering, IIT Kanpur (Fall 2026) · Project = 40% of grade,
> submitted in stages across the semester · Instructor: Priyanka Bagade · **CS455 does NOT use Agile/Scrum**
> (Lecture 1: *"We won't do any of this in CS455!"*) — structure work around the lifecycle below, not sprints.

---

## 0. Academic-integrity guardrail (read this first)

The logistics deck's dishonesty policy is strict: **any dishonesty = a non-negotiable F**, with random
plagiarism checks on reports. For GenAI (Claude, ChatGPT, Copilot):

| ✅ Allowed | ❌ Dishonesty → F |
|---|---|
| Use AI "like web" — learn concepts, research tools | Use AI to **create / decompose tasks** |
| **GitHub Copilot + VS Code for the code** | Use AI to **write / rewrite sections of any report** |
| (log AI use in the mandatory "GenAI use" sections) | Anything else not explicitly permitted |

**How the team + Claude split the work, safely:**
- **Claude helps** → explain concepts, research/compare tools, and write **code** (Copilot-style — log it),
  plus review your drafts by pointing out gaps against the course checklist.
- **The team owns** → all **report prose** (SRS, design docs, etc.) and the **Jira task breakdown + estimates**.

---

## 1. Project definition (our "same page")

**One-liner:** A web platform where several users join a shared room, edit the same code together in
real time (live cursors + presence), run it in a sandbox with shared output, and debug it collaboratively.

Mental model: **VS Code Live Share + Replit + a debugger**, scoped to a course project.

**Confirmed:** self-proposed topic (allowed) — it is the **2nd item** on the suggestion shortlist we worked
from. Locked in.

**Why this is genuine software engineering (the hard parts — this is what earns marks):**
1. **Concurrent editing** — merging simultaneous edits from many users without clobbering, via a
   **CRDT** or **Operational Transformation (OT)** algorithm. This is the intellectual core.
2. **Safe execution** — running *untrusted* user code in an isolated **sandbox** with CPU/memory/time
   limits and no network escape.
3. **Real-time resilience** — low-latency sync, presence, reconnection, and recovery after a server restart.

**Scope (draft — to confirm as a team):**
- **In (MVP):** create/join room · real-time collaborative editing with presence + cursors · run code in
  one language (e.g. Python) in a sandbox · shared stdout/stderr · run timeout · basic auth + room
  permissions · document persistence.
- **Stretch:** multiple languages · collaborative debugging (breakpoints / step-through) · test-case runner
  · version history / snapshots · in-room chat.
- **Out (explicitly not building):** full IDE IntelliSense/LSP · GPU execution · scaling to thousands of
  concurrent users · production-grade security hardening · mobile apps.

> Defining what you're **not** building is itself graded — the lifecycle calls it *scope*.

---

## 2. High-level architecture (to finalize together)

Three subsystems:

1. **Realtime collaboration** — editor client (Monaco or CodeMirror 6) ↔ WebSocket sync server. Conflict-free
   merging via a CRDT (e.g. Yjs) *or* a hand-written OT (writing your own is more work but a much stronger
   "engineering depth" story for the report). Separate presence/awareness channel for cursors.
2. **Execution sandbox** — an execution service that runs submitted code in an isolated environment
   (a Docker container per run, resource + wall-clock limits, network disabled) and streams stdout/stderr back.
3. **App + persistence** — REST + WebSocket API, auth, rooms, documents; a database (Postgres or SQLite);
   optional Redis for pub/sub fan-out if we run multiple server instances.

**Candidate tech (to decide based on team's strongest stack — this is "researching tools", which is allowed):**
- Frontend: React + Monaco Editor (or CodeMirror 6)
- Realtime/CRDT: Yjs + y-websocket, *or* a minimal custom OT to showcase the algorithm
- Backend: Node.js (pairs naturally with Yjs/WebSockets) *or* Python FastAPI (if the team is Python-first)
- Sandbox: Docker-per-run (simplest to reason about), or nsjail/firejail
- DB: Postgres · Cache/pubsub: Redis · Infra: Docker Compose · CI: GitHub Actions
- Static analysis: ESLint + (ruff/mypy or eslint/tsc) depending on language

---

## 3. Semester roadmap — phase by phase

Mapped to the 11 lifecycle stages from Lecture 1. Mostly sequential (waterfall/V-model style, as taught),
with iteration between design ↔ build ↔ test. **No dates yet** — the professor hasn't published the
submission schedule; we'll pin dates to phases once she does.

| # | Lifecycle stage | Goal for *this* project | Output artifact | CS455 grading hook |
|---|---|---|---|---|
| 1 | **Planning** | Lock scope, success criteria, roles | Project charter / pitch (½–1 pg) | Project mgmt (scope) |
| 2 | **Domain & technical analysis** | Model entities; pick CRDT-vs-OT & sandbox approach; de-risk with a throwaway spike | Domain model + spike notes | Architecture groundwork |
| 3 | **Requirements (FR + NFR)** | Write the SRS with *measurable* NFRs (latency, sandbox limits, recovery) + use cases | **SRS document** | Requirements *(team writes; Claude coaches)* |
| 4 | **Design & architecture** | Subsystem boundaries, APIs, data model, design patterns | Architecture doc + UML (class / sequence / component) | Design · UML · patterns |
| 5 | **UX/UI design + testing** | Editor / room / output / debugger UI; small usability test | Mockups + usability notes | UX |
| 6 | **Programming** | Build MVP, then stretch features | Working code (AI-assisted, logged) | Software health |
| 7 | **Debugging** | Find + fix a *real* defect (ideally the concurrent-edit lost-update bug) | Bug writeup: root cause + fix + regression test | Debugging · SE tools |
| 8 | **Testing** | Prove correctness + resilience | Unit/integration/system tests · failure-injection (kill executor mid-run) · perf (N editors, latency P50/P95) · coverage | Testing · resilience |
| 9 | **Documentation** | Full project docs | README · API spec · test & perf reports · user/system docs | Documentation |
| 10 | **Deployment / maintenance / change** | Ship it + evolve it | Docker Compose deploy · CI/CD · **one demonstrated requirement change** rippled through design/tests/docs | CI/CD · maintainability |
| 11 | **Project management** | Run it like adults | Jira board · estimates vs actuals · scope/time tradeoffs · process metrics | Project mgmt *(team owns the WBS)* |

---

## 4. "Graded-hard" checklist (CS455 priorities → concrete outputs)

From the "What is in CS455?" slide — these are what the professor said she cares about:

- **Software health** → clean code · design patterns (Strategy for merge policy, Observer for presence
  events, Factory for per-language executors) · UML · tests · static analysis · **GitHub + CI/CD**.
- **Software resilience** → sandbox isolation · run timeouts · executor-failure recovery · client
  reconnection · load/latency benchmarks under N concurrent editors.
- **Project management** → Jira · estimation · scope/time tradeoffs · metrics (LOC, cyclomatic complexity,
  coverage, latency percentiles).
- **SE tools** → real debugger usage · profiling the sync + execution hot paths.

---

## 5. Immediate next steps

1. **Finalize the pitch** — a 3–4 sentence project blurb; confirm with the prof/TAs if approval is needed.
2. **Set up infrastructure** — create the GitHub repo + Jira board (team does the account creation + task
   decomposition). Claude can scaffold the repo contents locally (README, folder structure, CI config) and
   propose a Jira epic/column structure for you to adapt.
3. **Tech spike** — a tiny "two clients type together + run one file" prototype to de-risk the hardest part
   (CRDT/OT + sandbox) before committing the architecture.
4. **Start the SRS** — the class is at Requirements now; Claude coaches FR/NFR + use-case elicitation, the
   team writes the document.

---
*Notes on the ChatGPT thread we worked from: its deep 20-step walkthrough and the MVP code it generated were
actually for two **other** ideas (Distributed Job Execution + Distributed File Storage), not this one. The
lifecycle *structure* transfers, but the specifics above are re-based onto the collaborative-code platform we
chose.*
