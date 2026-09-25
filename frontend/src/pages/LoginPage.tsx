import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../lib/api";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const tok = await api.login({ username, password });
      setToken(tok);
      navigate("/");
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "10vh auto", textAlign: "center" }}>
      <h2 style={{ marginBottom: 24 }}>Log in to Concord</h2>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: 8 }}>
        <input
          placeholder="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", background: "var(--panel)", color: "var(--fg)" }}
        />
        <input
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", background: "var(--panel)", color: "var(--fg)" }}
        />
        <button type="submit" disabled={loading || !username || !password}>
          {loading ? "Logging in..." : "Log in"}
        </button>
        {err && <div style={{ color: "var(--bad)", marginTop: 8, fontSize: 14 }}>{err}</div>}
      </form>
      <p style={{ marginTop: 16 }}>No account? <a href="/signup">Sign up</a></p>
    </div>
  );
}
