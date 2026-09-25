import { useEffect, useMemo, useRef, useState } from "react";
import Editor, { OnMount, Monaco } from "@monaco-editor/react";
import * as Y from "yjs";
import { MonacoBinding } from "y-monaco";
import { connectCollab, CollabConnection } from "../lib/ws";
import { api, CollabSession, FileMeta, getToken } from "../lib/api";
import { userColor } from "../lib/colors";

type DiffProposal = {
  original_text: string;
  proposed_text: string;
  explanation: string;
};

type EditorProps = {
  project: any;
  file: FileMeta;
  onExecEvent: (event: any) => void;
  onStructuralUpdate?: (msg: any) => void;
};

export default function CollabEditor({ project, file, onExecEvent, onStructuralUpdate, onCodeChange }: EditorProps & { onCodeChange?: (code: string) => void }) {
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const connRef = useRef<CollabConnection | null>(null);
  const bindingRef = useRef<MonacoBinding | null>(null);
  const onExecEventRef = useRef(onExecEvent);
  const onStructuralUpdateRef = useRef(onStructuralUpdate);
  const [breakpoints, setBreakpoints] = useState<number[]>([]);
  const [presence, setPresence] = useState<{ user_id: number; username: string; color: string }[]>([]);
  const [proposal, setProposal] = useState<DiffProposal | null>(null);

  // Keep the event ref up to date so the WS listener always uses the latest callback
  useEffect(() => {
    onExecEventRef.current = onExecEvent;
  }, [onExecEvent]);

  useEffect(() => {
    onStructuralUpdateRef.current = onStructuralUpdate;
  }, [onStructuralUpdate]);

  const user = useMemo(() => {
    const tok = getToken();
    if (!tok) return null;
    try {
      const payload = JSON.parse(atob(tok.split(".")[1]));
      return { id: payload.sub, username: payload.username || `user-${payload.sub}`, color: userColor(Number(payload.sub)) };
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!user) return;

    const wsBase = (import.meta.env.VITE_WS_URL as string | undefined) || "ws://127.0.0.1:8000";

    console.log("Establishing collab connection for project:", project.id, "file:", file.id);
    const conn = connectCollab({
      projectId: project.id,
      fileId: file.id,
      token: getToken()!,
      user,
      wsBase,
    });
    connRef.current = conn;

    // Set local awareness state so others can see our cursor, name, and color
    conn.awareness.setLocalState({
      user_id: user.id,
      username: user.username,
      color: user.color,
    });

    conn.awareness.on("change", () => {
      const seen = new Map<number, { user_id: number; username: string; color: string }>();
      conn.awareness.getStates().forEach((state: any) => {
        if (state?.user_id) seen.set(state.user_id, state);
      });
      const presenceList = Array.from(seen.values());
      console.log("Awareness states updated:", presenceList);
      setPresence(presenceList);
    });

    conn.ws.addEventListener("message", (event) => {
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data);
          if (msg.op === "exec_event") {
            onExecEventRef.current(msg.event);
          } else if (msg.op === "ai_assistant_response") {
            if (msg.proposal) {
              setProposal(msg.proposal);
            }
          } else if (msg.op === "project_presence") {
            if (onStructuralUpdateRef.current) onStructuralUpdateRef.current(msg);
          } else if (msg.op?.startsWith("WORKSPACE_")) {
            if (onStructuralUpdateRef.current) onStructuralUpdateRef.current(msg);
          }
        } catch { /* ignore */ }
      }
    });

    // Notify project that we are now editing this file
    conn.send({
      op: "project_presence",
      user_id: user.id,
      file_id: file.id,
    });

    if (editorRef.current && monacoRef.current) {
      setupBinding(editorRef.current, monacoRef.current, conn);
    }

    return () => {
      console.log("Cleaning up collab connection...");
      if (bindingRef.current) {
        bindingRef.current.destroy();
        bindingRef.current = null;
      }
      conn.close();
      connRef.current = null;
    };
  }, [project.id, file.id, user?.id]); // Stable dependencies: only reconnect on project/file/user change

  const setupBinding = (editor: any, monaco: Monaco, conn: CollabConnection) => {
    if (bindingRef.current) {
      bindingRef.current.destroy();
    }

    const ytext = conn.doc.getText("monaco");

    // Send initial content immediately
    if (onCodeChange) {
      onCodeChange(ytext.toString());
    }

    ytext.observe((event) => {
      if (conn.ws.readyState === WebSocket.OPEN) {
        conn.send({ op: "debug", message: `YText update: ${event.delta.length} changes` });
      }
      // Notify parent of code changes for AI context
      if (onCodeChange) {
        onCodeChange(ytext.toString());
      }
    });

    const model = editor.getModel();
    if (!model) return;

    const binding = new MonacoBinding(
      ytext,
      model,
      new Set([editor]),
      conn.awareness
    );
    bindingRef.current = binding;
    console.log("MonacoBinding successfully created");
  };

  const applyProposal = () => {
    if (!proposal || !connRef.current) return;
    const ytext = connRef.current.doc.getText("monaco");
    const currentText = ytext.toString();
    const index = currentText.indexOf(proposal.original_text);

    if (index !== -1) {
      ytext.delete(index, proposal.original_text.length);
      ytext.insert(index, proposal.proposed_text);
      setProposal(null);
    } else {
      alert("Could not find the original text to replace. The file may have changed.");
      setProposal(null);
    }
  };

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    if (connRef.current) {
      setupBinding(editor, monaco, connRef.current);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {proposal && (
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.8)", zIndex: 100, padding: 20,
          display: "flex", flexDirection: "column", gap: 16, color: "var(--fg)",
          overflowY: "auto", backdropFilter: "blur(4px)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>AI Proposal</h3>
            <button className="secondary" onClick={() => setProposal(null)}>Close</button>
          </div>
          <p style={{ opacity: 0.8, fontStyle: "italic" }}>{proposal.explanation}</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, height: "60%" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 12, opacity: 0.6 }}>Original</span>
              <pre style={{
                background: "var(--panel)", padding: 12, borderRadius: 4,
                overflow: "auto", fontSize: 12, border: "1px solid var(--border)",
                color: "#ffaaaa"
              }}>{proposal.original_text}</pre>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 12, opacity: 0.6 }}>Proposed</span>
              <pre style={{
                background: "var(--panel)", padding: 12, borderRadius: 4,
                overflow: "auto", fontSize: 12, border: "1px solid var(--border)",
                color: "#aaffaa"
              }}>{proposal.proposed_text}</pre>
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="secondary" onClick={() => setProposal(null)}>Reject</button>
            <button onClick={applyProposal}>Accept Change</button>
          </div>
        </div>
      )}
      <div className="presence-bar" style={{ padding: 4, gap: 6 }}>
        {presence.map((p) => (
          <span key={p.user_id} className="presence-dot" title={p.username || "Unknown"} style={{ background: p.color }}>
            {(p.username || "??").slice(-2)}
          </span>
        ))}
        {breakpoints.length > 0 && (
          <span style={{ marginLeft: "auto", fontSize: 11, opacity: 0.7 }}>
            breakpoints: {breakpoints.join(", ")}
          </span>
        )}
      </div>
      <div className="editor-host">
        <Editor
          height="100%"
          defaultLanguage={file.language || "python"}
          theme="vs-dark"
          onMount={handleMount}
          options={{
            fontSize: 13,
            minimap: { enabled: false },
            glyphMargin: true,
          }}
        />
      </div>
    </div>
  );
}
