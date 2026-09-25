import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getToken, Project, setToken } from "../lib/api";

export default function DashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [joinId, setJoinId] = useState("");
  const [memberId, setMemberId] = useState("");
  const [memberRole, setMemberRole] = useState("VIEWER");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refreshProjects() {
    try {
      const p = await api.listProjects();
      setProjects(p);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    if (!getToken()) navigate("/login");
    else refreshProjects();
  }, [navigate]);

  async function createProject() {
    if (!name.trim()) return;
    setLoading(true);
    try {
      const p = await api.createProject(name.trim());
      setProjects(prev => [...prev, p]);
      setName("");
      setErr(null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function openSession(project: Project) {
    navigate(`/projects/${project.id}`);
  }

  async function joinById() {
    if (!joinId.trim()) return;
    setLoading(true);
    try {
      await api.joinProject(Number(joinId));
      navigate(`/projects/${joinId}`);
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e);
      setErr(errMsg);
      alert(errMsg);
    } finally {
      setLoading(false);
    }
  }

  async function addMember(projectId: number) {
    if (!memberId.trim()) return;
    setLoading(true);
    try {
      const data = await api.addProjectMember(projectId, Number(memberId), memberRole);
      alert(data.message);
      setMemberId("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="layout">
      <header className="topbar">
        <strong style={{ fontSize: "1.2rem" }}>Concord</strong>
        <a href="/metrics" style={{ marginLeft: "auto" }}>Metrics</a>
        <button className="secondary" onClick={() => { setToken(null); navigate("/login"); }}>Log out</button>
      </header>

      <main className="main">
        <div className="dashboard-container">
          <div className="dashboard-header">
            <h1>My Projects</h1>
            <div style={{ display: "flex", gap: 8 }}>
               <button onClick={() => { setErr(null); refreshProjects(); }}>Refresh</button>
            </div>
          </div>

          <div className="action-grid">
            <div className="action-card">
              <h3>🚀 Create New Project</h3>
              <p style={{ opacity: 0.7, fontSize: "14px" }}>Start a new collaborative workspace with your team.</p>
              <div style={{ display: "grid", gap: 8 }}>
                <input
                  placeholder="Project name..."
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{ padding: "8px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", borderRadius: "4px" }}
                />
                <button onClick={createProject} disabled={loading || !name.trim()}>
                  {loading ? "Creating..." : "Create Project"}
                </button>
              </div>
            </div>

            <div className="action-card">
              <h3>🤝 Join Existing Project</h3>
              <p style={{ opacity: 0.7, fontSize: "14px" }}>Enter a project ID to jump in.</p>
              <div style={{ display: "grid", gap: 8 }}>
                <input
                  placeholder="Project ID"
                  value={joinId}
                  onChange={(e) => setJoinId(e.target.value)}
                  style={{ padding: "8px", background: "var(--bg)", border: "1px solid var(--border)", color: "var(--fg)", borderRadius: "4px" }}
                />
                <button onClick={joinById} className="secondary" disabled={loading || !joinId.trim()}>
                  {loading ? "Joining..." : "Join Project"}
                </button>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <h3>Your Active Projects</h3>
            {projects.length === 0 ? (
              <div style={{ textAlign: "center", padding: "40px", opacity: 0.5, border: "1px dashed var(--border)", borderRadius: "8px" }}>
                No projects found. Create one to get started!
              </div>
            ) : (
              <div className="project-grid">
                {projects.map((p) => (
                  <div key={p.id} className="project-card">
                    <div onClick={() => openSession(p)} style={{ cursor: "pointer", flex: 1 }}>
                      <h4 style={{ margin: 0 }}>{p.name}</h4>
                      <div className="meta">Project ID: #{p.id}</div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: "auto" }}>
                      <button onClick={() => openSession(p)}>Open Workspace</button>
                      <div style={{ display: "grid", gap: 4, padding: "8px", background: "var(--bg-alt)", borderRadius: "4px", fontSize: "12px" }}>
                        <strong>Add Member:</strong>
                        <div style={{ display: "flex", gap: 4 }}>
                          <input
                            placeholder="User ID"
                            value={memberId}
                            onChange={e => setMemberId(e.target.value)}
                            style={{ width: "60px", padding: "4px", background: "var(--bg)", color: "var(--fg)", border: "1px solid var(--border)", borderRadius: "2px" }}
                          />
                          <select
                            value={memberRole}
                            onChange={e => setMemberRole(e.target.value)}
                            style={{ padding: "4px", background: "var(--bg)", color: "var(--fg)", border: "1px solid var(--border)", borderRadius: "2px" }}
                          >
                            <option value="VIEWER">Viewer</option>
                            <option value="EDITOR">Editor</option>
                          </select>
                          <button onClick={() => addMember(p.id)} disabled={loading || !memberId.trim()}>Add</button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {err && (
            <div style={{
              backgroundColor: "rgba(248, 81, 73, 0.1)",
              border: "1px solid var(--bad)",
              color: "var(--bad)",
              padding: "12px",
              borderRadius: "8px",
              fontSize: "14px"
            }}>
              <strong>Error:</strong> {err}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
