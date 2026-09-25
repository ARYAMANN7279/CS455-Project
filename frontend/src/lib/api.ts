const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type Token = { access_token: string; token_type: string; user: User };
export type User = { id: number; username: string; email: string };
export type Project = { id: number; owner_id: number; name: string; created_at: string };
export type FolderMeta = { id: number; project_id: number; parent_folder_id: number | null; name: string; created_at: string };
export type FileMeta = { id: number; project_id: number; folder_id: number | null; path: string; language: string; created_at: string };
export type CollabSession = { id: number; project_id: number; created_by: number | null; status: string; created_at: string };
export type SessionMember = { session_id: number; user_id: number; role: string; joined_at: string };
export type Execution = {
  id: number; project_id: number; file_id: number; status: string;
  exit_code: number | null; stdout: string; stderr: string;
  queued_at: string; started_at: string | null; finished_at: string | null; worker_id: string | null;
};

export type ProjectMember = {
  user: User;
  role: string;
};

const tokenKey = "concord.token";
const userKey = "concord.user";

export function getToken(): string | null {
  return localStorage.getItem(tokenKey);
}

export function getUser(): User | null {
  const u = localStorage.getItem(userKey);
  return u ? JSON.parse(u) : null;
}

export function setToken(t: Token | null) {
  if (t) {
    localStorage.setItem(tokenKey, t.access_token);
    localStorage.setItem(userKey, JSON.stringify(t.user));
  } else {
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(userKey);
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  signup: (u: { username: string; email: string; password: string }) =>
    req<Token>("/auth/signup", { method: "POST", body: JSON.stringify(u) }),
  login: (u: { username: string; password: string }) =>
    req<Token>("/auth/login", { method: "POST", body: JSON.stringify(u) }),

  listProjects: () => req<Project[]>("/projects"),
  createProject: (name: string) => req<Project>("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  joinProject: (projectId: number) => req<{ session: CollabSession; role: string }>(`/projects/${projectId}/join`, { method: "POST" }),
  addProjectMember: (projectId: number, userId: number, role: string) =>
    req<{ message: string }>(`/projects/${projectId}/members`, { method: "POST", body: JSON.stringify({ user_id: userId, role }) }),
  listProjectMembers: (projectId: number) => req<ProjectMember[]>(`/projects/${projectId}/members`),
  removeProjectMember: (projectId: number, userId: number) =>
    req<void>(`/projects/${projectId}/members/${userId}`, { method: "DELETE" }),
  updateProjectMemberRole: (projectId: number, userId: number, role: string) =>
    req<ProjectMember>(`/projects/${projectId}/members/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) }),

  createSession: (projectId: number) =>
    req<CollabSession>(`/sessions/projects/${projectId}/sessions`, { method: "POST", body: JSON.stringify({}) }),
  joinSession: (sessionId: number) => req<{ session: CollabSession; role: string }>(`/sessions/join/${sessionId}`, { method: "POST" }),
  getProject: (projectId: number) => req<Project>(`/projects/${projectId}`),

  listFiles: (projectId: number) => req<FileMeta[]>(`/projects/${projectId}/files`),
  listFolders: (projectId: number) => req<FolderMeta[]>(`/projects/${projectId}/folders`),
  createFolder: (projectId: number, name: string, parentId: number | null = null) =>
    req<FolderMeta>(`/projects/${projectId}/folders`, { method: "POST", body: JSON.stringify({ name, parent_id: parentId }) }),
  updateFolder: (projectId: number, folderId: number, payload: { name?: string; parent_id?: number }) =>
    req<FolderMeta>(`/projects/${projectId}/folders/${folderId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  createFile: (projectId: number, path: string, folderId: number | null = null) =>
    req<FileMeta>(`/projects/${projectId}/files`, { method: "POST", body: JSON.stringify({ path, folder_id: folderId }) }),
  getFileContent: (projectId: number, fileId: number) =>
    req<{ file_id: number; text: string; version: number }>(`/projects/${projectId}/files/${fileId}/content`),
  updateFile: (projectId: number, fileId: number, payload: { path?: string; folder_id?: number }) =>
    req<FileMeta>(`/projects/${projectId}/files/${fileId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  run: (projectId: number, fileId: number) =>
    req<Execution>(`/projects/${projectId}/executions`, { method: "POST", body: JSON.stringify({ file_id: fileId }) }),
  listExecutions: (projectId: number) => req<Execution[]>(`/projects/${projectId}/executions`),
  cancelExecution: (projectId: number, executionId: number) =>
    req<Execution>(`/projects/${projectId}/executions/${executionId}/cancel`, { method: "POST", body: JSON.stringify({}) }),

  listBreakpoints: (projectId: number, fileId: number) =>
    req<{ id: number; file_id: number; line: number; enabled: boolean; created_by: number | null; created_at: string }[]>(
      `/projects/${projectId}/breakpoints?file_id=${fileId}`
    ),
  upsertBreakpoints: (projectId: number, payload: { file_id: number; line: number; enabled: boolean }[]) =>
    req(`/projects/${projectId}/breakpoints`, { method: "PUT", body: JSON.stringify(payload) }),
  requestAssistant: (projectId: number, payload: { prompt: string }) =>
    req<any>(`/projects/${projectId}/assist`, { method: "POST", body: JSON.stringify(payload) }),
  metricsSummary: () => req<{ status_counts: Record<string, number>; avg_runtime_seconds: number }>("/metrics/executions/summary"),
  metricsRecent: () => req<{ events: { id: number; event_type: string; created_at: string; payload: unknown } }>(`/metrics/events/recent`),
};
