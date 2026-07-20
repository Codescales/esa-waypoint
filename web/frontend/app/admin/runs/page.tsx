"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import Link from "next/link";
import {
  getRuns,
  getRunners,
  getStreams,
  adminPatchRun,
  createRun,
  deleteRun,
  type Run,
  type RunPatch,
  type RunnerDTO,
  type RunCreateRequest,
} from "@/lib/api";

type SortKey = "time" | "game";

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

function RunnerSelectorCell({
  participants,
  runners,
  onSave,
  onUpdated,
}: {
  participants: Run["participants"];
  runners: RunnerDTO[];
  onSave: (slugs: string[]) => Promise<Run>;
  onUpdated: (run: Run) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) {
      setSelected(participants.map((p) => p.slug));
    }
  }, [editing, participants]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setEditing(false);
      }
    }
    if (editing) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [editing]);

  function toggle(slug: string) {
    setSelected((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]
    );
  }

  async function commit() {
    setSaving(true);
    setError("");
    try {
      const updated = await onSave(selected);
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
      <td className="py-2 pr-3 relative">
        <div ref={ref} className="absolute z-50 bg-surface border border-border rounded shadow-lg p-2 min-w-[200px] max-h-[300px] overflow-y-auto">
          <div className="flex flex-col gap-1 mb-2">
            {runners.map((r) => (
              <label key={r.slug} className="flex items-center gap-2 text-xs cursor-pointer hover:bg-brand/10 px-1 py-0.5 rounded">
                <input
                  type="checkbox"
                  checked={selected.includes(r.slug)}
                  onChange={() => toggle(r.slug)}
                  disabled={saving}
                  className="accent-brand"
                />
                {r.display_name || r.slug}
              </label>
            ))}
          </div>
          <div className="flex items-center gap-2 border-t border-border pt-1">
            <button onClick={commit} disabled={saving} className="text-xs px-2 py-0.5 bg-brand text-white rounded hover:opacity-80">
              {saving ? "..." : "Save"}
            </button>
            <button onClick={() => setEditing(false)} className="text-xs px-2 py-0.5 text-muted hover:text-foreground">
              Cancel
            </button>
            {error && <span className="text-xs text-remove" title={error}>!</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {participants.length === 0 ? (
            <span className="text-muted/50 text-xs">—</span>
          ) : (
            participants.map((p) => (
              <Link
                key={p.slug}
                href={`/runner/${p.slug}`}
                className="hover:text-brand transition-colors text-xs"
              >
                {p.display_name || p.slug}
              </Link>
            ))
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
      <div className="flex flex-wrap gap-1">
        {participants.length === 0 ? (
          <span className="text-muted/50 text-xs">—</span>
        ) : (
          participants.map((p) => (
            <Link
              key={p.slug}
              href={`/runner/${p.slug}`}
              className="hover:text-brand transition-colors text-xs"
              onClick={(e) => e.stopPropagation()}
            >
              {p.display_name || p.slug}
            </Link>
          ))
        )}
      </div>
    </td>
  );
}

export default function AdminRunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runners, setRunners] = useState<RunnerDTO[]>([]);
  const [streams, setStreams] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    Promise.all([
      getRuns({ marathon: true }),
      getRunners(),
      getStreams(),
    ])
      .then(([runsData, runnersData, streamsData]) => {
        setRuns(runsData);
        setRunners(runnersData);
        setStreams(streamsData);
      })
      .finally(() => setLoading(false));
  }, []);

  function updateRun(updated: Run) {
    setRuns((prev) => prev.map((r) => (r.slug === updated.slug ? updated : r)));
  }

  function addRun(created: Run) {
    setRuns((prev) => [...prev, created]);
  }

  function removeRun(slug: string) {
    setRuns((prev) => prev.filter((r) => r.slug !== slug));
  }

  async function handleCreate(body: RunCreateRequest) {
    const created = await createRun(body);
    addRun(created);
    setShowAddForm(false);
  }

  async function handleDelete(slug: string) {
    if (!window.confirm("Delete this run? This cannot be undone.")) return;
    try {
      await deleteRun(slug);
      removeRun(slug);
    } catch (e) {
      console.error("Delete failed", e);
      alert(String(e));
    }
  }

  function patch(slug: string, field: keyof RunPatch) {
    return (val: string) =>
      adminPatchRun(slug, { [field]: val });
  }

  function patchRunners(slug: string) {
    return (slugs: string[]) =>
      adminPatchRun(slug, { runner_slugs: slugs });
  }

  const filtered = useMemo(() => {
    let f = search
      ? runs.filter(
          (r) =>
            r.game.toLowerCase().includes(search.toLowerCase()) ||
            r.runner_display.toLowerCase().includes(search.toLowerCase()) ||
            r.category.toLowerCase().includes(search.toLowerCase())
        )
      : runs;
    if (sortKey === "game") {
      f = [...f].sort((a, b) => a.game.localeCompare(b.game));
    } else {
      f = [...f].sort((a, b) => new Date(a.scheduled).getTime() - new Date(b.scheduled).getTime());
    }
    return f;
  }, [runs, search, sortKey]);

  function toggleSort(key: SortKey) {
    setSortKey(key);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Runs</h1>
        <p className="text-sm text-muted">{filtered.length} of {runs.length}</p>
      </div>

      <div className="flex flex-wrap gap-3 mb-4 items-center">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by game, runner, or category…"
          className="input input-sm w-full max-w-sm"
        />
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="btn btn-sm ml-auto"
        >
          {showAddForm ? "cancel" : "new run"}
        </button>
      </div>

      {showAddForm && (
        <AddRunForm
          streams={streams}
          onSubmit={handleCreate}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th
                  className="pb-2 pr-3 font-medium cursor-pointer hover:text-brand select-none"
                  onClick={() => toggleSort("time")}
                >
                  Time{sortKey === "time" ? " \u25B2" : ""}
                </th>
                <th className="pb-2 pr-3 font-medium">Stream</th>
                <th
                  className="pb-2 pr-3 font-medium cursor-pointer hover:text-brand select-none"
                  onClick={() => toggleSort("game")}
                >
                  Game{sortKey === "game" ? " \u25B2" : ""}
                </th>
                <th className="pb-2 pr-3 font-medium">Category</th>
                <th className="pb-2 pr-3 font-medium">Runners</th>
                <th className="pb-2 pr-3 font-medium">Commentator</th>
                <th className="pb-2 pr-3 font-medium">Pronouns</th>
                <th className="pb-2 pr-3 font-medium">Show Cam</th>
                <th className="pb-2 pr-3 font-medium">Runner Comments</th>
                <th className="pb-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.slug} className="border-b border-border/50 hover:bg-surface/80">
                  <td className="py-2 pr-3 font-mono text-xs whitespace-nowrap">
                    {new Date(r.scheduled).toLocaleDateString("en-GB", {
                      day: "2-digit",
                      month: "2-digit",
                      timeZone: "Europe/Stockholm",
                    })}{" "}
                    {new Date(r.scheduled).toLocaleTimeString("en-GB", {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: "Europe/Stockholm",
                    })}
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted">{r.stream_short}</td>
                  <td className="py-2 pr-3">
                    <Link
                      href={`/run/${r.slug}`}
                      className="hover:text-brand transition-colors font-medium"
                    >
                      {r.game}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 text-muted text-xs">{r.category}</td>
                  <RunnerSelectorCell
                    participants={r.participants}
                    runners={runners}
                    onSave={patchRunners(r.slug)}
                    onUpdated={updateRun}
                  />
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
                  <td className="py-2 pr-3">
                    <button
                      onClick={() => handleDelete(r.slug)}
                      className="text-xs text-muted hover:text-remove transition-colors px-1"
                      title="Delete run"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddRunForm({
  streams,
  onSubmit,
  onCancel,
}: {
  streams: string[];
  onSubmit: (body: RunCreateRequest) => Promise<void>;
  onCancel: () => void;
}) {
  const [scheduled, setScheduled] = useState("");
  const [game, setGame] = useState("");
  const [category, setCategory] = useState("");
  const [estimate, setEstimate] = useState("");
  const [platform, setPlatform] = useState("");
  const [players, setPlayers] = useState("");
  const [stream, setStream] = useState(streams[0] || "");
  const [streamShort, setStreamShort] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!scheduled || !game.trim() || !category.trim()) return;
    setSaving(true);
    setError("");
    try {
      await onSubmit({
        scheduled,
        game: game.trim(),
        category: category.trim(),
        estimate: estimate || undefined,
        platform: platform || undefined,
        players: players || undefined,
        stream: stream || undefined,
        stream_short: streamShort || stream || undefined,
      });
      setGame("");
      setCategory("");
      setEstimate("");
      setPlatform("");
      setPlayers("");
      setScheduled("");
      setStreamShort("");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-4 p-4 card space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Scheduled *
          </label>
          <input
            type="datetime-local"
            value={scheduled}
            onChange={(e) => setScheduled(e.target.value)}
            required
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Game *
          </label>
          <input
            type="text"
            value={game}
            onChange={(e) => setGame(e.target.value)}
            required
            placeholder="Super Mario 64"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Category *
          </label>
          <input
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            required
            placeholder="120 Star"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Estimate
          </label>
          <input
            type="text"
            value={estimate}
            onChange={(e) => setEstimate(e.target.value)}
            placeholder="1:30:00"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Platform
          </label>
          <input
            type="text"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            placeholder="N64"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Players
          </label>
          <input
            type="text"
            value={players}
            onChange={(e) => setPlayers(e.target.value)}
            placeholder="1"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Stream
          </label>
          <select
            value={stream}
            onChange={(e) => setStream(e.target.value)}
            className="input input-sm"
          >
            <option value="">—</option>
            {streams.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Stream short
          </label>
          <input
            type="text"
            value={streamShort}
            onChange={(e) => setStreamShort(e.target.value)}
            placeholder="stream1"
            className="input input-sm"
          />
        </div>
      </div>
      {error && <p className="text-xs text-remove">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!scheduled || !game.trim() || !category.trim() || saving}
          className="btn btn-sm"
        >
          {saving ? "adding…" : "add run"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="btn btn-sm btn-b2"
        >
          cancel
        </button>
      </div>
    </form>
  );
}
