"use client";

import { useEffect, useState, FormEvent, useCallback, useRef } from "react";
import {
  adminLogin,
  adminStatus,
  adminRefresh,
  adminSnapshots,
  adminRestore,
  adminAudit,
  listJobs,
  getJob,
  cancelJob,
  syncSchedule,
  syncBriefs,
  syncRunners,
  type AdminStatus,
  type AdminSnapshot,
  type AdminAuditEntry,
  type AdminRefreshResult,
  type JobDTO,
} from "@/lib/api";

type JobSummary = { step: string; detail: string };

export default function AdminPage() {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState<boolean | null>(null); // null = checking
  const [error, setError] = useState("");
  const [status, setStatus] = useState<AdminStatus | null>(null);
  const [snapshots, setSnapshots] = useState<AdminSnapshot[]>([]);
  const [audit, setAudit] = useState<AdminAuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // Active jobs polling state
  const [jobs, setJobs] = useState<JobDTO[]>([]);
  // Tracked sync jobs: id -> { status, summary }
  const [syncJobs, setSyncJobs] = useState<Record<string, JobDTO>>({});
  const jobsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncIntervalsRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  async function refreshStatus(): Promise<boolean> {
    try {
      const [s, sn, au] = await Promise.all([
        adminStatus(),
        adminSnapshots(),
        adminAudit(20),
      ]);
      setStatus(s);
      setSnapshots(sn);
      setAudit(au);
      return true;
    } catch {
      setAuthed(false);
      return false;
    }
  }

  const loadJobs = useCallback(async () => {
    try {
      const j = await listJobs({ limit: 10 });
      setJobs(j);
    } catch {
      // silently fail on polling
    }
  }, []);

  useEffect(() => {
    refreshStatus().then((ok) => {
      if (ok) setAuthed(true);
    });
  }, []);

  useEffect(() => {
    if (authed) {
      loadJobs();
      jobsIntervalRef.current = setInterval(loadJobs, 3000);
      return () => {
        if (jobsIntervalRef.current) clearInterval(jobsIntervalRef.current);
      };
    }
  }, [authed, loadJobs]);

  function startPollingJob(jobId: string) {
    if (syncIntervalsRef.current[jobId]) return;
    const iv = setInterval(async () => {
      try {
        const j = await getJob(jobId);
        setSyncJobs((prev) => ({ ...prev, [jobId]: j }));
        if (j.status === "succeeded" || j.status === "failed") {
          clearInterval(iv);
          delete syncIntervalsRef.current[jobId];
        }
      } catch {
        clearInterval(iv);
        delete syncIntervalsRef.current[jobId];
      }
    }, 1500);
    syncIntervalsRef.current[jobId] = iv;
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await adminLogin(password);
      setPassword("");
      setAuthed(true);
      await refreshStatus();
    } catch {
      setError("Invalid admin password");
    }
  }

  async function handleRefresh() {
    if (!confirm("Refresh the database from the latest xlsx? A snapshot will be taken first.")) return;
    setBusy(true);
    setFlash(null);
    try {
      const r: AdminRefreshResult = await adminRefresh();
      if (r.ok) {
        setFlash({ kind: "ok", msg: `Refreshed: +${r.runs_added} runs, +${r.incentives_added} incentives. Snapshot: ${r.snapshot_id}` });
      } else {
        setFlash({ kind: "err", msg: `Refresh failed: ${r.error}` });
      }
      await refreshStatus();
    } catch (e) {
      setFlash({ kind: "err", msg: String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function handleRestore(snapId: string) {
    if (!confirm(`Restore from snapshot ${snapId}? A pre-restore snapshot will be taken first. The current DB will be replaced.`)) return;
    setBusy(true);
    setFlash(null);
    try {
      const r: AdminRefreshResult = await adminRestore(snapId);
      if (r.ok) {
        setFlash({ kind: "ok", msg: `Restored from ${snapId}` });
      } else {
        setFlash({ kind: "err", msg: `Restore failed: ${r.error}` });
      }
      await refreshStatus();
    } catch (e) {
      setFlash({ kind: "err", msg: String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function triggerSync(
    fn: () => Promise<JobDTO>,
    label: string
  ) {
    setFlash(null);
    try {
      const job = await fn();
      setSyncJobs((prev) => ({ ...prev, [job.id]: job }));
      startPollingJob(job.id);
      setFlash({ kind: "ok", msg: `${label} started (job ${job.id.slice(0, 8)})` });
    } catch (err: any) {
      const msg: string = err?.message || String(err);
      if (msg.includes("409")) {
        // Extract existing job id from detail if possible
        const parts = msg.split(":");
        const detail = parts[parts.length - 1]?.trim();
        if (detail) {
          setFlash({ kind: "err", msg: `${label} already running (job ${detail.slice(0, 8)}). Polling…` });
          setSyncJobs((prev) => ({ ...prev, [detail]: prev[detail] }));
          startPollingJob(detail);
        } else {
          setFlash({ kind: "err", msg: `${label} already running` });
        }
      } else {
        setFlash({ kind: "err", msg: `${label} failed: ${msg}` });
      }
    }
  }

  async function handleCancel(jobId: string) {
    try {
      await cancelJob(jobId);
      await loadJobs();
      const updated = await getJob(jobId);
      setSyncJobs((prev) => ({ ...prev, [jobId]: updated }));
    } catch (e) {
      setFlash({ kind: "err", msg: `Cancel failed: ${String(e)}` });
    }
  }

  function parseSummary(json: string): JobSummary[] {
    try {
      const parsed = JSON.parse(json);
      if (Array.isArray(parsed)) return parsed as JobSummary[];
    } catch {
      // ignore
    }
    return [];
  }

  const activeSyncs = Object.values(syncJobs);

  if (authed === null) {
    return <p className="text-muted text-sm mt-8">Loading...</p>;
  }

  if (!authed) {
    return (
      <div className="max-w-md mx-auto mt-12">
        <form
          onSubmit={handleLogin}
          className="p-6 card space-y-4"
        >
          <h1 className="text-xl font-bold">Admin Login</h1>
          <p className="text-sm text-muted">
            Admin operations require a separate password. Hosts cannot see this page.
          </p>
          {error && (
            <p className="text-sm text-remove bg-remove/10 px-3 py-2 rounded">{error}</p>
          )}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Admin password"
            className="input"
            autoFocus
          />
          <button
            type="submit"
            className="btn w-full"
          >
            log in
          </button>
          <p className="text-xs text-muted">
            <a href="/" className="hover:underline">← Back to marathon</a>
          </p>
        </form>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Admin</h1>
        <p className="text-sm text-muted">Operator controls. Session expires in 1 hour.</p>
      </div>

      {flash && (
        <div
          className={`p-3 rounded text-sm ${
            flash.kind === "ok" ? "flash-ok" : "flash-err"
          }`}
        >
          {flash.msg}
        </div>
      )}

      {/* Sync buttons */}
      <section className="card p-5">
        <h2 className="text-lg font-bold mb-3">Sync</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => triggerSync(syncSchedule, "Sync Schedule")}
            disabled={busy}
            className="btn btn-sm"
          >
            sync schedule
          </button>
          <button
            onClick={() => triggerSync(syncBriefs, "Sync Briefs")}
            disabled={busy}
            className="btn btn-sm"
          >
            sync briefs
          </button>
          <button
            onClick={() => triggerSync(() => syncRunners(), "Sync Runners")}
            disabled={busy}
            className="btn btn-sm"
          >
            sync runners
          </button>
        </div>
        {activeSyncs.length > 0 && (
          <div className="mt-4 space-y-3">
            {activeSyncs.map((j) => {
              const summary = parseSummary(j.summary_json);
              const isDone = j.status === "succeeded" || j.status === "failed";
              return (
                <div key={j.id} className="text-sm border border-border rounded p-3">
                  <div className="flex items-center gap-2">
                    {!isDone && (
                      <span className="inline-block w-3 h-3 border-2 border-brand border-t-transparent rounded-full animate-spin" />
                    )}
                    <span className="font-medium capitalize">{j.kind}</span>
                    <span
                      className={
                        j.status === "succeeded"
                          ? "pill pill-approve"
                          : j.status === "failed"
                          ? "pill pill-remove"
                          : "pill pill-review"
                      }
                    >
                      {j.status}
                    </span>
                    {j.target && <span className="text-muted text-xs">target: {j.target}</span>}
                  </div>
                  {j.error && <p className="text-remove text-xs mt-1">{j.error}</p>}
                  {summary.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-xs text-muted">
                      {summary.map((s, i) => (
                        <li key={i}>
                          • {s.step}: {s.detail}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Status */}
      <section className="card p-5 space-y-2">
        <h2 className="text-lg font-bold mb-3">Database Status</h2>
        {status ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="text-muted">Exists</dt>
            <dd>{status.db_exists ? "yes" : "no"}</dd>
            <dt className="text-muted">Healthy</dt>
            <dd>{status.db_healthy ? "yes" : "no"}</dd>
            <dt className="text-muted">Schema version</dt>
            <dd>{status.schema_version}</dd>
            <dt className="text-muted">Size</dt>
            <dd>{(status.db_size_bytes / 1024).toFixed(1)} KB</dd>
            <dt className="text-muted">Last import</dt>
            <dd>{status.last_import_at ?? "—"}</dd>
            <dt className="text-muted">Runs</dt>
            <dd>{status.counts.runs}</dd>
            <dt className="text-muted">Incentives</dt>
            <dd>{status.counts.incentives}</dd>
            <dt className="text-muted">Notes</dt>
            <dd>{status.counts.notes}</dd>
            <dt className="text-muted">Hosts</dt>
            <dd>{status.counts.hosts}</dd>
            <dt className="text-muted">Snapshots on disk</dt>
            <dd>{status.counts.snapshots}</dd>
          </dl>
        ) : (
          <p className="text-muted">Loading...</p>
        )}
      </section>

      {/* Active jobs */}
      <section className="card p-5">
        <h2 className="text-lg font-bold mb-3">Active Jobs</h2>
        {jobs.length === 0 ? (
          <p className="text-muted text-sm">No jobs yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-border">
                <th className="text-left pb-2 font-medium">Kind</th>
                <th className="text-left pb-2 font-medium">Status</th>
                <th className="text-left pb-2 font-medium">Target</th>
                <th className="text-left pb-2 font-medium">Created</th>
                <th className="text-right pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const summary = parseSummary(j.summary_json);
                const canCancel = j.status === "pending" || j.status === "running";
                return (
                  <tr key={j.id} className="border-b border-border/50 align-top">
                    <td className="py-2 capitalize">{j.kind}</td>
                    <td className="py-2">
                      <span
                        className={
                          j.status === "succeeded"
                            ? "pill pill-approve"
                            : j.status === "failed"
                            ? "pill pill-remove"
                            : "pill pill-review"
                        }
                      >
                        {j.status}
                      </span>
                    </td>
                    <td className="py-2 text-muted">{j.target || "—"}</td>
                    <td className="py-2 text-muted text-xs">{new Date(j.created_at).toLocaleString()}</td>
                    <td className="py-2 text-right">
                      {canCancel && (
                        <button
                          onClick={() => handleCancel(j.id)}
                          className="btn btn-sm"
                          style={{ background: "transparent", color: "var(--red)", border: "2px solid var(--red)", textShadow: "none" }}
                        >
                          cancel
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* Refresh */}
      <section className="card p-5">
        <h2 className="text-lg font-bold mb-2">Refresh from xlsx</h2>
        <p className="text-sm text-muted mb-3">
          Re-imports the schedule spreadsheet into the SQLite database. A snapshot is
          taken first so you can restore if the import goes wrong. User edits (incentive
          status changes via the UI) are preserved across re-imports.
        </p>
        <button
          onClick={handleRefresh}
          disabled={busy}
          className="btn btn-sm"
        >
          {busy ? "refreshing…" : "refresh now"}
        </button>
      </section>

      {/* Snapshots */}
      <section className="card p-5">
        <h2 className="text-lg font-bold mb-3">Snapshots</h2>
        {snapshots.length === 0 ? (
          <p className="text-muted text-sm">No snapshots yet. Snapshots are created automatically before each refresh/restore.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-border">
                <th className="text-left pb-2 font-medium">ID</th>
                <th className="text-left pb-2 font-medium">Size</th>
                <th className="text-left pb-2 font-medium">Age</th>
                <th className="text-left pb-2 font-medium">Schema</th>
                <th className="text-right pb-2 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.id} className="border-b border-border/50">
                  <td className="py-2 font-mono text-xs">{s.id}</td>
                  <td className="py-2">{(s.size_bytes / 1024).toFixed(1)} KB</td>
                  <td className="py-2">{s.age_hours.toFixed(1)}h</td>
                  <td className="py-2">{s.schema_version}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => handleRestore(s.id)}
                      disabled={busy}
                      className="btn btn-sm btn-b4"
                    >
                      restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Audit log */}
      <section className="card p-5">
        <h2 className="text-lg font-bold mb-3">Recent activity</h2>
        {audit.length === 0 ? (
          <p className="text-muted text-sm">No admin actions yet.</p>
        ) : (
          <ul className="space-y-1 text-xs font-mono">
            {audit.slice().reverse().map((e, i) => (
              <li key={i} className="text-gray-600">
                <span className="text-gray-400">{e.timestamp}</span>{" "}
                <span className="font-bold text-gray-700">{e.action}</span>{" "}
                {e.detail}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
