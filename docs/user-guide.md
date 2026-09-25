# Concord — User Guide

## Getting started

1. Open the app in your browser.
2. Sign up with a username, email, and password.
3. From the dashboard, click **Create** to make a new project, then click the
   project to open a collaboration session.
4. The session shows a file tree on the left, an editor in the middle, and
   a console at the bottom.

## Real-time collaboration

- Anyone you invite to the session edits the same file. You'll see their
  cursor as a colored dot in the editor and in the presence bar above it.
- Edits are CRDT-merged — even if you both type at the same line, no edits
  are lost.
- If you lose your network connection briefly, the editor reconnects
  automatically and re-syncs the missing updates.

## Running code

1. Click **Run** in the sidebar.
2. The console at the bottom shows the job lifecycle: `queued → starting →
   running → completed` (or `failed`/`timeout`/`cancelled`).
3. Click **Cancel** to stop a long-running job.

## Debugging

1. Click on the line number in the editor's gutter to set a breakpoint.
   The line number gets a red dot.
2. Click **Run** as usual — the container starts with `debugpy` listening,
   and execution pauses on your first breakpoint.
3. Use the step controls (continue / step over / step in / step out) to
   walk through the code.
4. The variables and call stack appear in the side panel.

Only the user who clicks **Step** drives the debugger. Other session
members see the same paused state, call stack, and variables live.

## Snapshots

- **Save snapshot:** click the snapshot button in the sidebar. Give it a
  name like "v1 — works on small input".
- **Restore:** click a snapshot in the history panel. The live editor for
  all connected users reverts to that state.
- Use snapshots before risky edits; they cost nothing.

## Roles

| Role | Can do |
|---|---|
| viewer | read code, watch runs and debug, no edits |
| editor | everything viewer can + edit + run + take snapshots |
| debugger | everything editor can + set breakpoints + step |
| owner | everything + manage members and change roles |

The session owner is the only one who can change roles. Default for new
joiners is viewer.
