"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { getRuns, adminPatchRun, type Run, type RunPatch } from "@/lib/api";

function EditableTextCell({
  value,
  onSave,
  onUpdated,
  children,
}: {
  value: string;
  onSave: (val: string) => Promise<Run>;
  onUpdated: (run: Run) => void;
  children: React.ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && ref.current) {
      ref.current.focus();
      ref.current.select();
    }
  }, [editing]);

  async function commit() {
    if (draft === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await onSave(draft);
      onUpdated(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      setEditing(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") {
      setDraft(value);
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <td className="py-2 pr-3">
        <div className="flex items-center gap-1">
          <input
            ref={ref}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={handleKeyDown}
            disabled={saving}
            className="w-full px-1 py-0.5 text-xs border border-brand rounded bg-surface"
          />
          {error && (
            <span className="text-xs text-remove shrink-0" title={error}>!</span>
          )}
          {saved && (
            <span className="text-xs text-approve shrink-0">✓</span>
          )}
        </div>
      </td>
    );
  }

  return (
    <td
      className="py-2 pr-3 cursor-pointer hover:bg-surface/50"
      onClick={() => {
        setDraft(value);
        setEditing(true);
      }}
    >
      {children}
    </td>
  );
}

function EditableSelectCell({
  value,
  options,
  onSave,
  onUpdated,
  children,
}: {
  value: string;
  options: string[];
  onSave: (val: string) => Promise<Run>;
  onUpdated: (run: Run) => void;
  children: React.ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    if (editing && ref.current) ref.current.focus();
  }, [editing]);

  async function commit(newVal: string) {
    if (newVal === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await onSave(newVal);
      onUpdated(updated);
      setEditing(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <td className="py-2 pr-3">
        <div className="flex items-center gap-1">
          <select
            ref={ref}
            defaultValue={value}
            onChange={(e) => commit(e.target.value)}
            disabled={saving}
            className="w-full px-1 py-0.5 text-xs border border-brand rounded bg-surface"
          >
            {options.map((o) => (
              <option key={o} value={o}>{o || "—"}</option>
            ))}
          </select>
          {error && (
            <span className="text-xs text-remove shrink-0" title={error}>!</span>
          )}
        </div>
      </td>
    );
  }

  return (
    <td
      className="py-2 pr-3 cursor-pointer hover:bg-surface/50"
      onClick={() => setEditing(true)}
    >
      {children}
    </td>
  );
}

const SHOW_CAM_OPTIONS = ["", "Yes", "No", "If possible"];

export default function AdminRunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getRuns({ marathon: true })
      .then((data) => setRuns(data))
      .finally(() => setLoading(false));
  }, []);

  function updateRun(updated: Run) {
    setRuns((prev) => prev.map((r) => (r.slug === updated.slug ? updated : r)));
  }

  function patch(slug: string, field: keyof RunPatch) {
    return (val: string) =>
      adminPatchRun(slug, { [field]: val });
  }

  const filtered = search
    ? runs.filter(
        (r) =>
          r.game.toLowerCase().includes(search.toLowerCase()) ||
          r.runner_display.toLowerCase().includes(search.toLowerCase()) ||
          r.category.toLowerCase().includes(search.toLowerCase())
      )
    : runs;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Runs</h1>
        <p className="text-sm text-muted">{filtered.length} of {runs.length}</p>
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by game, runner, or category…"
        className="input input-sm mb-4 w-full max-w-sm"
      />

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th className="pb-2 pr-3 font-medium">Game</th>
                <th className="pb-2 pr-3 font-medium">Category</th>
                <th className="pb-2 pr-3 font-medium">Runner</th>
                <th className="pb-2 pr-3 font-medium">Commentator</th>
                <th className="pb-2 pr-3 font-medium">Pronouns</th>
                <th className="pb-2 pr-3 font-medium">Show Cam</th>
                <th className="pb-2 pr-3 font-medium">Runner Comments</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.slug} className="border-b border-border/50 hover:bg-surface/80">
                  <td className="py-2 pr-3">
                    <Link
                      href={`/run/${r.slug}`}
                      className="hover:text-brand transition-colors font-medium"
                    >
                      {r.game}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 text-muted text-xs">{r.category}</td>
                  <td className="py-2 pr-3">
                    <Link
                      href={`/runner/${r.runner_slug}`}
                      className="hover:text-brand transition-colors text-xs"
                    >
                      {r.runner_display}
                    </Link>
                  </td>
                  <EditableTextCell
                    value={r.commentator}
                    onSave={patch(r.slug, "commentator")}
                    onUpdated={updateRun}
                  >
                    <span className="text-xs">{r.commentator || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <EditableTextCell
                    value={r.pronouns}
                    onSave={patch(r.slug, "pronouns")}
                    onUpdated={updateRun}
                  >
                    <span className="text-xs">{r.pronouns || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <EditableSelectCell
                    value={r.show_cam}
                    options={SHOW_CAM_OPTIONS}
                    onSave={patch(r.slug, "show_cam")}
                    onUpdated={updateRun}
                  >
                    <span className="text-xs">{r.show_cam || <span className="text-muted/50">—</span>}</span>
                  </EditableSelectCell>
                  <EditableTextCell
                    value={r.runner_comments}
                    onSave={patch(r.slug, "runner_comments")}
                    onUpdated={updateRun}
                  >
                    <span className="text-xs max-w-[200px] truncate block" title={r.runner_comments}>
                      {r.runner_comments || <span className="text-muted/50">—</span>}
                    </span>
                  </EditableTextCell>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
