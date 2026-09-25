import * as Y from "yjs";
import {
  Awareness,
  applyAwarenessUpdate,
  encodeAwarenessUpdate,
} from "y-protocols/awareness";

export type CollabMessage =
  | { op: "hello" }
  | { op: "sync_step1"; sv: string }
  | { op: "awareness"; state: { user_id: number; username: string; cursor?: { line: number; col: number }; color: string } }
  | { op: "awareness_update"; data: string }
  | { op: "exec_event"; event: any }
  | { op: "presence"; states: any[] }
  | { op: "project_presence"; user_id: number; file_id: number | null }
  | { op: "error"; message: string };

// We tag local edits with this origin so we don't echo them back into the doc
// when the server forwards the same update to other clients in this room.
const REMOTE_ORIGIN = Symbol("concord:remote");

export type ProjectConnection = {
  ws: WebSocket;
  send: (msg: any) => void;
  close: () => void;
};

export function connectProject(opts: {
  projectId: number;
  token: string;
  wsBase: string;
}): ProjectConnection {
  const url = `${opts.wsBase}/ws/projects/${opts.projectId}?token=${encodeURIComponent(opts.token)}`;
  const ws = new WebSocket(url);

  return {
    ws,
    send(msg: any) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
    },
    close() {
      try { ws.close(); } catch { /* noop */ }
    },
  };
}

export function connectCollab(opts: {
  projectId: number;
  fileId: number;
  token: string;
  user: { id: number; username: string; color: string };
  wsBase: string;
}): CollabConnection {
  const url = `${opts.wsBase}/ws/projects/${opts.projectId}/files/${opts.fileId}?token=${encodeURIComponent(opts.token)}`;
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  const doc = new Y.Doc();
  const awareness = new Awareness(doc);
  const pendingUpdates: Uint8Array[] = [];

  ws.addEventListener("open", () => {
    console.log("WebSocket connected to:", url);
    ws.send(JSON.stringify({ op: "hello" }));

    // Start heartbeat ping to verify connection is actually alive
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: "ping" }));
      } else {
        clearInterval(pingInterval);
      }
    }, 10000);

    while (pendingUpdates.length > 0) {
      const update = pendingUpdates.shift();
      if (update) {
        console.log("Flushing pending update of size:", update.length);
        const b64Update = btoa(String.fromCharCode(...update));
        ws.send(JSON.stringify({ op: "update", data: b64Update }));
      }
    }
  });

  ws.addEventListener("message", (event) => {
    if (event.data instanceof ArrayBuffer) {
      // CRDT update from server: apply to our local doc, tagged with REMOTE_ORIGIN
      // so the outbound `doc.on('update', ...)` handler below ignores it.
      Y.applyUpdate(doc, new Uint8Array(event.data), REMOTE_ORIGIN);
    } else if (typeof event.data === "string") {
      try {
        const msg: CollabMessage = JSON.parse(event.data);
        if (msg.op === "awareness_update") {
          console.log("WS: Received awareness_update, data length:", msg.data?.length);
          const update = new Uint8Array(
            atob(msg.data).split("").map((c) => c.charCodeAt(0))
          );
          applyAwarenessUpdate(awareness, update, REMOTE_ORIGIN);
          console.log("WS: Awareness update applied. Current states:", awareness.getStates().size);
        } else if (msg.op === "presence" && Array.isArray(msg.states)) {
          // Correctly apply remote states to the local awareness instance
          msg.states.forEach((s) => {
            if (typeof s.client_id === "number") {
              awareness.setState(s.client_id, {
                user_id: s.user_id,
                username: s.username,
                color: s.color,
                cursor: s.cursor,
              });
            }
          });
        }
      } catch {
        // ignore non-JSON
      }
    }
  });

  // Forward local doc edits upstream.
  doc.on("update", (update: Uint8Array, origin: unknown) => {
    // DEBUG: Log every update and its origin to find out why they are being dropped
    console.log("Yjs Doc update triggered. Origin:", origin, "Update size:", update.length);

    if (origin === REMOTE_ORIGIN) {
      console.log("Update ignored: origin is REMOTE_ORIGIN");
      return;
    }

    // Instead of raw binary, send as Base64 JSON to avoid proxy/firewall issues with binary frames
    const b64Update = btoa(String.fromCharCode(...update));
    const msg = JSON.stringify({ op: "update", data: b64Update });

    if (ws.readyState === WebSocket.OPEN) {
      console.log("Sending Base64 update to server...");
      ws.send(msg);
    } else {
      console.log("WebSocket not open, buffering update");
      pendingUpdates.push(update);
    }
  });

  // Push local awareness changes upstream.
  awareness.on("update", () => {
    if (ws.readyState === WebSocket.OPEN) {
      const update = encodeAwarenessUpdate(awareness, [awareness.getClientId()]);
      const b64Update = btoa(String.fromCharCode(...update));
      ws.send(JSON.stringify({
        op: "awareness_update",
        data: b64Update,
      }));
    }
  });

  return {
    ws,
    doc,
    awareness,
    send(msg: CollabMessage | Uint8Array) {
      if (msg instanceof Uint8Array) {
        if (ws.readyState === WebSocket.OPEN) ws.send(msg);
      } else {
        if (ws.readyState === WebSocket.OPEN) {
          const payload = typeof msg === "string" ? msg : JSON.stringify(msg);
          ws.send(payload);
        }
      }
    },
    close() {
      try { ws.close(); } catch { /* noop */ }
    },
  };
}
