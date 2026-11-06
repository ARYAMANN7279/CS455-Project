import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { friendlyError } from "../lib/errors";

type ExecutionSummary = Awaited<ReturnType<typeof api.metricsSummary>>;
type RecentEvent = Awaited<ReturnType<typeof api.metricsRecent>>["events"][number];

export default function MetricsPage() {
  const [summary, setSummary] = useState<ExecutionSummary | null>(null);
  const [recent, setRecent] = useState<RecentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([api.metricsSummary(), api.metricsRecent()])
      .then(([nextSummary, nextRecent]) => {
        if (!active) return;
        setSummary(nextSummary);
        setRecent(nextRecent.events);
      })
      .catch((reason: unknown) => {
        if (active) setError(friendlyError(reason));
      });
    return () => { active = false; };
  }, []);

  return (
    <div style={{ padding: 24 }}>
      <h1>Metrics</h1>
      {error ? <p role="alert">{error}</p> : (
        <>
          <h3>Execution summary</h3>
          {summary ? (
            <pre>{JSON.stringify(summary, null, 2)}</pre>
          ) : (
            <p>loading…</p>
          )}
          <h3>Recent events</h3>
          {recent.length === 0 ? <p>none yet</p> : (
            <table style={{ borderCollapse: "collapse" }}>
              <thead><tr><th align="left">id</th><th align="left">event</th><th align="left">at</th></tr></thead>
              <tbody>
                {recent.map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td>{e.event_type}</td>
                    <td>{e.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
