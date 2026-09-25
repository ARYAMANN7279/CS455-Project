import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, Project, Execution, FileMeta, FolderMeta, getToken, getUser, ProjectMember } from "../lib/api";
import { connectProject } from "../lib/ws";
import CollabEditor from "../components/Editor";
import FileTree from "../components/FileTree";
import ErrorBoundary from "../components/ErrorBoundary";

export default function SessionPage() {
  console.log("SessionPage: Component is rendering");
  const { projectId } = useParams<{ projectId: string }>();
  console.log("SessionPage: projectId from params:", projectId);
  const navigate = useNavigate();
  const pid = Number(projectId);
  console.log("SessionPage: pid (number):", pid);
  const [project, setProject] = useState<Project | null>(null);
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [folders, setFolders] = useState<FolderMeta[]>([]);
  const [active, setActive] = useState<FileMeta | null>(null);
  const [activeFolder, setActiveFolder] = useState<FolderMeta | null>(null);
  const [presence, setPresence] = useState<Record<number, number>>({});
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([]);
  const [membersModal, setMembersModal] = useState<"list" | "add" | null>(null);
  const [memberForm, setMemberForm] = useState({ userId: "", role: "viewer" });
  const [exec, setExec] = useState<Execution | null>(null);
  const [execLog, setExecLog] = useState<{ status: string; ts: number; text?: string }[]>([]);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiHistory, setAiHistory] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const [aiContext, setAiContext] = useState("");
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [modal, setModal] = useState<{
    mode: "create" | "rename";
    type: "file" | "folder";
    name: string;
    targetId?: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    console.log("SessionPage: useEffect loadProjectData triggered");
    if (!getToken()) {
      console.log("SessionPage: No token found, navigating to login");
      navigate("/login");
      return;
    }
    if (!pid || isNaN(pid)) {
      console.log("SessionPage: Invalid pid:", pid);
      setError("Invalid project ID");
      return;
    }

    async function loadProjectData() {
      try {
        console.log("SessionPage: Loading project data for pid:", pid);
        const p = await api.getProject(pid);
        console.log("SessionPage: API getProject returned:", p);

        if (!p) {
          console.log("SessionPage: Project not found");
          setError("Project not found");
          return;
        }

        console.log("SessionPage: Project loaded successfully:", p.name);
        setProject(p);

        Promise.all([
          api.listProjectMembers(pid).then(m => {
            console.log("SessionPage: Members loaded:", m);
            setMembers(m || []);
          }).catch(e => console.error("SessionPage: Failed to load members:", e)),
          api.listExecutions(pid).catch(e => console.error("SessionPage: Failed to load executions:", e))
        ]);

        const [fs, flds] = await Promise.all([
          api.listFiles(p.id),
          api.listFolders(p.id)
        ]);
        console.log("SessionPage: Files and folders loaded. Files:", fs?.length, "Folders:", flds?.length);
        setFiles(fs || []);
        setFolders(flds || []);
        if (fs && fs.length > 0) {
          console.log("SessionPage: Setting active file:", fs[0].path);
          setActive(fs[0]);
        }
      } catch (err) {
        console.error("SessionPage: ERROR in loadProjectData:", err);
        setError(err instanceof Error ? err.message : "An unexpected error occurred while loading the project.");
      }
    }

    loadProjectData();
  }, [pid, navigate]);

  const onStructuralUpdate = useCallback((msg: any) => {
    const { op, file, folder, folder_id, user_id, file_id } = msg;
    if (op === "WORKSPACE_FILE_CREATED") {
      setFiles(prev => [...prev, file]);
      setActive(prev => prev || file);
    } else if (op === "WORKSPACE_FILE_UPDATED") {
      setFiles(prev => {
        const idx = prev.findIndex(f => f.id === file.id);
        if (idx !== -1) {
          const next = [...prev];
          next[idx] = file;
          return next;
        }
        return [...prev, file];
      });
    } else if (op === "WORKSPACE_FILE_DELETED") {
      setFiles(prev => prev.filter(f => f.id !== file_id));
      setActive(prev => prev?.id === file_id ? null : prev);
    } else if (op === "WORKSPACE_FOLDER_CREATED" || op === "WORKSPACE_FOLDER_UPDATED") {
      setFolders(prev => {
        const idx = prev.findIndex(f => f.id === folder.id);
        if (idx !== -1) {
          const next = [...prev];
          next[idx] = folder;
          return next;
        }
        return [...prev, folder];
      });
    } else if (op === "WORKSPACE_FOLDER_DELETED") {
      setFolders(prev => prev.filter(f => f.id !== folder_id));
    } else if (op === "project_presence") {
      setPresence(prev => ({ ...prev, [user_id]: file_id }));
    }
  }, []);

  useEffect(() => {
    if (active) {
      setAiContext(""); // Clear context when switching files to avoid sending wrong file content
    }
  }, [active]);

  useEffect(() => {
    if (!pid || isNaN(pid)) return;
    if (!project) return;

    console.log("SessionPage: Establishing project WS connection");
    const wsBase = (import.meta.env.VITE_WS_URL as string | undefined) || "ws://127.0.0.1:8000";
    const projConn = connectProject({
      projectId: pid,
      token: getToken()!,
      wsBase,
    });

    projConn.ws.addEventListener("message", (event) => {
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data);
          if (msg.op?.startsWith("WORKSPACE_")) {
            onStructuralUpdate(msg);
          }
        } catch { /* ignore */ }
      }
    });

    return () => {
      console.log("SessionPage: Closing project WS connection");
      projConn.close();
    };
  }, [pid, project, onStructuralUpdate]);

  const onExecEvent = useCallback((event: any) => {
    if (event.type === "execution_output") {
      setExecLog((prev) => [...prev, { status: "output", ts: Date.now(), text: event.stdout + (event.stderr ? `\n[stderr]\n${event.stderr}` : "") }]);
    } else if (event.type === "execution_status") {
      setExecLog((prev) => [...prev, { status: event.status, ts: Date.now() }]);
      setExec((cur) => (cur && cur.id === event.execution_id ? { ...cur, status: event.status } : cur));
    } else if (event.type === "debug_paused") {
      setExecLog((prev) => [...prev, { status: "paused", ts: Date.now(), text: JSON.stringify(event, null, 2) }]);
    } else if (event.type === "debug_running" || event.type === "debug_stopped") {
      setExecLog((prev) => [...prev, { status: event.type, ts: Date.now() }]);
    }
  }, []);

  async function handleAiRequest() {
    if (!aiPrompt.trim() || !project) return;
    const prompt = aiPrompt;
    setAiPrompt("");
    setAiHistory(prev => [...prev, { role: "user", text: prompt }]);
    setIsAiLoading(true);

    console.log("AI Request triggered. Context being sent:", aiContext ? `Length: ${aiContext.length}` : "EMPTY");

    try {
      const response = await api.requestAssistant(project.id, {
        prompt,
        context_code: aiContext
      });
      setAiHistory(prev => [...prev, { role: "assistant", text: response.response }]);
    } catch (e) {
      setAiHistory(prev => [...prev, { role: "assistant", text: "Error: " + (e instanceof Error ? e.message : "Unknown error") }]);
    } finally {
      setIsAiLoading(false);
    }
  }

  async function runActive() {
    if (!active || !project) return;
    try {
      const e = await api.run(project.id, active.id);
      setExec(e);
      setExecLog((prev) => [...prev, { status: "queued", ts: Date.now(), text: `execution #${e.id} queued` }]);

      // FALLBACK: Poll for status if WebSocket is slow/broken
      const pollInterval = setInterval(async () => {
        try {
          const current = await api.getExecution(project.id, e.id);
          if (current.status !== "queued" && current.status !== "starting") {
            setExec(current);
            // If it finished, we can stop polling
            if (["completed", "failed", "timeout", "cancelled"].includes(current.status)) {
              clearInterval(pollInterval);
            }
          }
        } catch (err) {
          console.error("Polling error:", err);
        }
      }, 2000);

      // Stop polling if execution is cancelled or replaced
      return () => clearInterval(pollInterval);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function cancel() {
    if (!exec) return;
    try {
      await api.cancelExecution(project.id, exec.id);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function loadProjectMembers() {
    if (!project) return;
    try {
      const pm = await api.listProjectMembers(project.id);
      setProjectMembers(pm || []);
    } catch (e) {
      console.error("Failed to load project members:", e);
    }
  }

  async function handleCreate() {
    if (!project || !modal) return;
    try {
      if (modal.type === "file") {
        if (!activeFolder) {
          alert("Please select a folder first to create a file inside it.");
          return;
        }
        const f = await api.createFile(project.id, modal.name, activeFolder.id);
        setFiles(prev => [...prev, f]);
        setActive(f);
      } else {
        const parentId = activeFolder?.id || null;
        const f = await api.createFolder(project.id, modal.name, parentId);
        setFolders(prev => [...prev, f]);
      }
      setModal(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleRename() {
    if (!project || !modal || !modal.targetId) return;
    try {
      if (modal.type === "file") {
        const f = await api.updateFile(project.id, modal.targetId, { path: modal.name });
        setFiles(prev => {
          const idx = prev.findIndex(f => f.id === modal.targetId);
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = f;
            return next;
          }
          return [...prev, f];
        });
        if (active?.id === modal.targetId) setActive(f);
      } else {
        const f = await api.updateFolder(project.id, modal.targetId, { name: modal.name });
        setFolders(prev => {
          const idx = prev.findIndex(f => f.id === modal.targetId);
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = f;
            return next;
          }
          return [...prev, f];
        });
      }
      setModal(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleAddMember() {
    if (!project) return;

    if (memberForm.userId === "") {
      alert("Please enter a User ID or Username.");
      return;
    }

    try {
      await api.addProjectMember(project.id, memberForm.userId, memberForm.role);
      await loadProjectMembers();
      setMembersModal(null);
      setMemberForm({ userId: "", role: "viewer" });
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleRemoveMember(userId: number) {
    if (!project) return;
    try {
      await api.removeProjectMember(project.id, userId);
      await loadProjectMembers();
    } catch (e) {
      console.error("Failed to remove project member:", e);
    }
  }

  async function handleUpdateRole(userId: number, role: string) {
    if (!project) return;
    try {
      await api.updateProjectMemberRole(project.id, userId, role);
      await loadProjectMembers();
    } catch (e) {
      alert("Failed to update role");
    }
  }

  if (error) return <div style={{ padding: 24, color: "var(--bad)", background: "var(--bg)", height: "100vh", border: "5px solid red" }}>Error: {error}</div>;
  if (!project) return <div style={{ padding: 24, background: "red", height: "100vh", color: "white", border: "5px solid yellow" }}>Loading project...</div>;

  console.log("SessionPage: Rendering UI. Project:", project);
  return (
    <ErrorBoundary>
      <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw", overflow: "hidden", background: "var(--bg)", color: "var(--fg)", boxSizing: "border-box" }}>
        <header className="topbar" style={{ flexShrink: 0, height: 40, display: "flex", alignItems: "center", padding: "0 12px", background: "var(--panel)", borderBottom: "1px solid var(--border)" }}>
          <strong style={{ marginRight: 12 }}>Concord</strong>
          <span style={{ opacity: 0.7, marginRight: "auto" }}>Project: {project.name}</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {members.map((m) => (
              <span key={m.user.id} className={`role-pill ${m.role}`} style={{ fontSize: 10 }}>
                {m.role}#{m.user.id}
              </span>
            ))}
            {project.owner_id === (getUser() || {id: -1})?.id && (
              <button
                onClick={async () => {
                  await loadProjectMembers();
                  setMembersModal("list");
                }}
                className="secondary"
                style={{ marginLeft: 12 }}
              >
                Members
              </button>
            )}
            <button onClick={() => navigate("/")} className="secondary" style={{ marginLeft: 12 }}>Back</button>
          </div>
        </header>
        <div style={{ display: "flex", flexGrow: 1, overflow: "hidden" }}>
          <aside className="sidebar" style={{ width: 220, background: "var(--panel)", borderRight: "1px solid var(--border)", padding: 8, overflowY: "auto", zIndex: 10 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 12 }}>
              <button onClick={() => setModal({ mode: "create", type: "file", name: "" })} className="secondary" style={{ cursor: "pointer" }}>+ New file</button>
              <button onClick={() => setModal({ mode: "create", type: "folder", name: "" })} className="secondary" style={{ cursor: "pointer" }}>+ New folder</button>
            </div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Files</h3>
            <FileTree
              files={files}
              folders={folders}
              activeFileId={active?.id || null}
              activeFolderId={activeFolder?.id || null}
              onSelectFile={(f) => {
                setActive(f);
                setActiveFolder(null);
              }}
              onSelectFolder={(f) => {
                setActiveFolder(f);
                setActive(null);
              }}
              onRename={(type, item) => {
                setModal({
                  mode: "rename",
                  type,
                  name: type === "file" ? (item as FileMeta).path : (item as FolderMeta).name,
                  targetId: (item as any).id,
                });
              }}
              presence={presence}
            />
            {active && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                <button onClick={runActive} disabled={exec && (exec.status === "queued" || exec.status === "starting" || exec.status === "running")} style={{ width: "100%", marginBottom: 4 }}>
                  Run
                </button>
                <button onClick={cancel} disabled={!exec || ["completed", "failed", "timeout", "cancelled"].includes(exec.status)} className="secondary" style={{ width: "100%" }}>
                  Cancel
                </button>
                {exec && <div style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>status: {exec.status}</div>}
              </div>
            )}
          </aside>
          <main className="main" style={{ flexGrow: 1, position: "relative", overflow: "hidden" }}>
            {active ? (
              <div style={{ display: "flex", flexDirection: "row", height: "100%" }}>
                <div style={{ flexGrow: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                  <CollabEditor
                    project={project}
                    file={active}
                    onExecEvent={onExecEvent}
                    onStructuralUpdate={onStructuralUpdate}
                    onCodeChange={(code) => setAiContext(code)}
                  />
                  <div className="bottom-panel" style={{ height: 200, borderTop: "1px solid var(--border)", background: "var(--panel)", padding: 8, overflowY: "auto", fontFamily: "monospace", fontSize: 12 }}>
                    <strong style={{ display: "block", marginBottom: 4 }}>Console</strong>
                    <div>
                      {execLog.map((l, i) => (
                        <div key={i} style={{ color: l.status === "failed" || l.status === "timeout" ? "var(--bad)" : "var(--fg)", marginBottom: 2 }}>
                          [{new Date(l.ts).toLocaleTimeString()}] {l.status}
                          {l.text ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{l.text}</pre> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <aside style={{ width: 300, background: "var(--panel)", borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
                  <div style={{ padding: 12, borderBottom: "1px solid var(--border)", fontWeight: "bold" }}>AI Assistant</div>
                  <div style={{ flexGrow: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
                    {aiHistory.map((msg, i) => (
                      <div key={i} style={{ alignSelf: msg.role === "user" ? "flex-end" : "flex-start", background: msg.role === "user" ? "var(--accent)" : "var(--bg)", padding: 8, borderRadius: 8, fontSize: 13, maxWidth: "80%", color: "var(--fg)" }}>
                        {msg.text}
                      </div>
                    ))}
                    {isAiLoading && <div style={{ alignSelf: "flex-start", background: "var(--bg)", padding: 8, borderRadius: 8, fontSize: 13, opacity: 0.6 }}>AI is thinking...</div>}
                  </div>
                  <div style={{ padding: 12, borderTop: "1px solid var(--border)", display: "flex", gap: 8 }}>
                    <input
                      value={aiPrompt}
                      onChange={e => setAiPrompt(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && handleAiRequest()}
                      placeholder="Ask AI..."
                      style={{ flexGrow: 1, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", padding: 8, borderRadius: 4 }}
                    />
                    <button onClick={handleAiRequest} disabled={isAiLoading} style={{ padding: "8px 12px" }}>Send</button>
                  </div>
                </aside>
              </div>
            ) : (
              <div style={{ padding: 24, display: "flex", alignItems: "center", justifyContent: "center", height: "100%", opacity: 0.5 }}>
                Pick a file or folder to get started.
              </div>
            )}
          </main>
        </div>
        {modal && (
          <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: "rgba(0,0,0,0.7)", display: "flex",
            alignItems: "center", justifyContent: "center", zIndex: 1000
          }}>
            <div style={{
              background: "var(--panel)", padding: 24, borderRadius: 8,
              border: "1px solid var(--border)", width: 300, display: "flex",
              flexDirection: "column", gap: 12
            }}>
              <h3 style={{ margin: 0 }}>{modal.mode === "create" ? `Create ${modal.type === "file" ? "File" : "Folder"}` : `Rename ${modal.type === "file" ? "File" : "Folder"}`}</h3>
              <input
                autoFocus
                placeholder={modal.type === "file" ? "file_name.py" : "folder_name"}
                value={modal.name}
                onChange={(e) => setModal({ ...modal, name: e.target.value })}
                style={{ padding: 8, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", borderRadius: 4 }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
                <button className="secondary" onClick={() => setModal(null)}>Cancel</button>
                <button onClick={modal.mode === "create" ? handleCreate : handleRename}>
                  {modal.mode === "create" ? "Create" : "Rename"}
                </button>
              </div>
            </div>
          </div>
        )}

        {membersModal && (
          <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: "rgba(0,0,0,0.7)", display: "flex",
            alignItems: "center", justifyContent: "center", zIndex: 1000
          }}>
            <div style={{
              background: "var(--panel)", padding: 24, borderRadius: 8,
              border: "1px solid var(--border)", width: 400, display: "flex",
              flexDirection: "column", gap: 12
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ margin: 0 }}>Project Members</h3>
                <button
                  onClick={() => setMembersModal(membersModal === "list" ? "add" : "list")}
                  className="secondary"
                  style={{ fontSize: 12 }}
                >
                  {membersModal === "list" ? "+ Add Member" : "Back to List"}
                </button>
              </div>

              {membersModal === "list" ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 400, overflowY: "auto" }}>
                  {projectMembers.map((m) => (
                    <div key={m.user.id} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: 8, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <strong>{m.user.username}</strong>
                        <span className={`role-pill ${m.role}`} style={{ fontSize: 10 }}>{m.role}</span>
                        {project?.owner_id === (getUser() || {id: -1})?.id && m.user.id !== project?.owner_id && (
                          <select
                            value={m.role?.toLowerCase()}
                            onChange={e => handleUpdateRole(m.user.id, e.target.value)}
                            style={{ fontSize: 10, padding: "2px", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--fg)" }}
                          >
                            <option value="viewer">Viewer</option>
                            <option value="editor">Editor</option>
                            <option value="debugger">Debugger</option>
                            <option value="owner">Owner</option>
                          </select>
                        )}
                      </div>
                      {m.user.id !== project?.owner_id && (
                        <button
                          onClick={() => handleRemoveMember(m.user.id)}
                          className="secondary"
                          style={{ fontSize: 10, color: "var(--bad)" }}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  ))}
                  {projectMembers.length === 0 && <div style={{ textAlign: "center", opacity: 0.5 }}>No members found.</div>}
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>User ID or Username</label>
                    <input
                      autoFocus
                      placeholder="e.g. 123 or username"
                      value={memberForm.userId}
                      onChange={(e) => setMemberForm({ ...memberForm, userId: e.target.value })}
                      style={{ width: "100%", padding: 8, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", borderRadius: 4 }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>Role</label>
                    <select
                      value={memberForm.role}
                      onChange={(e) => setMemberForm({ ...memberForm, role: e.target.value })}
                      style={{ width: "100%", padding: 8, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", borderRadius: 4 }}
                    >
                      <option value="viewer">Viewer</option>
                      <option value="editor">Editor</option>
                      <option value="debugger">Debugger</option>
                      <option value="owner">Owner</option>
                    </select>
                  </div>
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
                    <button className="secondary" onClick={() => setMembersModal("list")}>Cancel</button>
                    <button onClick={handleAddMember}>Add Member</button>
                  </div>
                </div>
              )}

              <button
                onClick={() => setMembersModal(null)}
                className="secondary"
                style={{ marginTop: 12 }}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
