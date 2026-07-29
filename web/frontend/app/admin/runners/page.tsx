"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  getRunners,
  adminPatchRunner,
  createRunner,
  deleteRunner,
  mergeRunners,
  type RunnerDTO,
  type RunnerPatch,
  type RunnerCreateRequest,
} from "@/lib/api";

function EditableTextCell({
  value,
  onSave,
  onUpdated,
  children,
}: {
  value: string;
  onSave: (val: string) => Promise<RunnerDTO>;
  onUpdated: (runner: RunnerDTO) => void;
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

export default function AdminRunnersPage() {
  const [runners, setRunners] = useState<RunnerDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [survivorSlug, setSurvivorSlug] = useState<string | null>(null);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState("");

  useEffect(() => {
    getRunners()
      .then((data) => setRunners(data))
      .finally(() => setLoading(false));
  }, []);

  function updateRunner(updated: RunnerDTO) {
    setRunners((prev) => prev.map((r) => (r.slug === updated.slug ? updated : r)));
  }

  function addRunner(created: RunnerDTO) {
    setRunners((prev) => [...prev, created]);
  }

  function removeRunner(slug: string) {
    setRunners((prev) => prev.filter((r) => r.slug !== slug));
  }

  function toggleSelected(slug: string) {
    setMergeError("");
    setSelected((prev) => {
      if (prev.includes(slug)) {
        const next = prev.filter((s) => s !== slug);
        if (survivorSlug === slug) setSurvivorSlug(null);
        return next;
      }
      if (prev.length >= 2) return prev; // cap at 2 for a merge
      const next = [...prev, slug];
      if (next.length === 1) setSurvivorSlug(slug);
      return next;
    });
  }

  function clearSelection() {
    setSelected([]);
    setSurvivorSlug(null);
    setMergeError("");
  }

  async function handleMerge() {
    if (selected.length !== 2 || !survivorSlug) return;
    const duplicateSlug = selected.find((s) => s !== survivorSlug)!;
    const survivor = runners.find((r) => r.slug === survivorSlug);
    const duplicate = runners.find((r) => r.slug === duplicateSlug);
    if (
      !window.confirm(
        `Merge "${duplicate?.display_name}" into "${survivor?.display_name}"?\n\n` +
          `All runs and notes will move to "${survivor?.display_name}", and ` +
          `"${duplicate?.display_name}" will be deleted. This cannot be undone.`
      )
    )
      return;
    setMerging(true);
    setMergeError("");
    try {
      const updated = await mergeRunners(survivorSlug, duplicateSlug);
      setRunners((prev) =>
        prev
          .filter((r) => r.slug !== duplicateSlug)
          .map((r) => (r.slug === updated.slug ? updated : r))
      );
      clearSelection();
    } catch (e) {
      setMergeError(String(e));
    } finally {
      setMerging(false);
    }
  }

  async function handleCreate(body: RunnerCreateRequest) {
    const created = await createRunner(body);
    addRunner(created);
    setShowAddForm(false);
  }

  async function handleDelete(slug: string) {
    if (!window.confirm("Delete this runner? This cannot be undone.")) return;
    try {
      await deleteRunner(slug);
      removeRunner(slug);
    } catch (e) {
      console.error("Delete failed", e);
      alert(String(e));
    }
  }

  function patch(slug: string, field: keyof RunnerPatch) {
    return (val: string) => adminPatchRunner(slug, { [field]: val });
  }

  const filtered = search
    ? runners.filter(
        (r) =>
          r.display_name.toLowerCase().includes(search.toLowerCase()) ||
          r.twitch.toLowerCase().includes(search.toLowerCase())
      )
    : runners;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Runners</h1>
        <p className="text-sm text-muted">{filtered.length} of {runners.length}</p>
      </div>

      <div className="flex flex-wrap gap-3 mb-4 items-center">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or Twitch handle…"
          className="input input-sm w-full max-w-sm"
        />
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="btn btn-sm ml-auto"
        >
          {showAddForm ? "cancel" : "new runner"}
        </button>
      </div>

      {showAddForm && (
        <AddRunnerForm
          onSubmit={handleCreate}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {selected.length > 0 && (
        <div className="mb-4 p-3 card flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted">
            {selected.length === 1
              ? "Select one more runner to merge."
              : "Choose which runner to keep (survivor):"}
          </span>
          {selected.length === 2 && (
            <div className="flex items-center gap-3">
              {selected.map((slug) => {
                const r = runners.find((x) => x.slug === slug);
                return (
                  <label key={slug} className="flex items-center gap-1 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name="survivor"
                      checked={survivorSlug === slug}
                      onChange={() => setSurvivorSlug(slug)}
                      className="accent-brand"
                    />
                    {r?.display_name || slug}
                  </label>
                );
              })}
              <button
                onClick={handleMerge}
                disabled={merging || !survivorSlug}
                className="btn btn-sm"
              >
                {merging ? "merging…" : "merge"}
              </button>
            </div>
          )}
          <button onClick={clearSelection} className="btn btn-sm btn-b2">
            cancel
          </button>
          {mergeError && <span className="text-xs text-remove" title={mergeError}>merge failed</span>}
        </div>
      )}

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th className="pb-2 pr-3 font-medium"></th>
                <th className="pb-2 pr-3 font-medium">Name</th>
                <th className="pb-2 pr-3 font-medium">Pronouns</th>
                <th className="pb-2 pr-3 font-medium">Pronunciation</th>
                <th className="pb-2 pr-3 font-medium">Twitch</th>
                <th className="pb-2 pr-3 font-medium">Discord</th>
                <th className="pb-2 pr-3 font-medium">Twitter</th>
                <th className="pb-2 pr-3 font-medium">Runs</th>
                <th className="pb-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.slug} className="border-b border-border/50 hover:bg-surface/80">
                  <td className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={selected.includes(r.slug)}
                      disabled={!selected.includes(r.slug) && selected.length >= 2}
                      onChange={() => toggleSelected(r.slug)}
                      className="accent-brand"
                      title="Select to merge"
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <Link
                      href={`/runner/${r.slug}`}
                      className="hover:text-brand transition-colors font-medium"
                    >
                      {r.display_name}
                    </Link>
                  </td>
                  <EditableTextCell
                    value={r.pronouns}
                    onSave={patch(r.slug, "pronouns")}
                    onUpdated={updateRunner}
                  >
                    <span className="text-xs">{r.pronouns || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <EditableTextCell
                    value={r.pronunciation}
                    onSave={patch(r.slug, "pronunciation")}
                    onUpdated={updateRunner}
                  >
                    <span className="text-xs">{r.pronunciation || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <EditableTextCell
                    value={r.twitch}
                    onSave={patch(r.slug, "twitch")}
                    onUpdated={updateRunner}
                  >
                    <span className="text-xs">{r.twitch || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <EditableTextCell
                    value={r.discord}
                    onSave={patch(r.slug, "discord")}
                    onUpdated={updateRunner}
                  >
                    <span className="text-xs">{r.discord || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <EditableTextCell
                    value={r.twitter}
                    onSave={patch(r.slug, "twitter")}
                    onUpdated={updateRunner}
                  >
                    <span className="text-xs">{r.twitter || <span className="text-muted/50">—</span>}</span>
                  </EditableTextCell>
                  <td className="py-2 pr-3 text-xs text-muted">{r.run_count}</td>
                  <td className="py-2 pr-3">
                    <button
                      onClick={() => handleDelete(r.slug)}
                      className="text-xs text-muted hover:text-remove transition-colors px-1"
                      title="Delete runner"
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

function AddRunnerForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (body: RunnerCreateRequest) => Promise<void>;
  onCancel: () => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [twitch, setTwitch] = useState("");
  const [discord, setDiscord] = useState("");
  const [twitter, setTwitter] = useState("");
  const [pronouns, setPronouns] = useState("");
  const [pronunciation, setPronunciation] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!displayName.trim()) return;
    setSaving(true);
    setError("");
    try {
      await onSubmit({
        display_name: displayName.trim(),
        twitch: twitch.trim() || undefined,
        discord: discord.trim() || undefined,
        twitter: twitter.trim() || undefined,
        pronouns: pronouns.trim() || undefined,
        pronunciation: pronunciation.trim() || undefined,
      });
      setDisplayName("");
      setTwitch("");
      setDiscord("");
      setTwitter("");
      setPronouns("");
      setPronunciation("");
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
            Display name *
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            placeholder="Runner name"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Twitch
          </label>
          <input
            type="text"
            value={twitch}
            onChange={(e) => setTwitch(e.target.value)}
            placeholder="twitchhandle"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Discord
          </label>
          <input
            type="text"
            value={discord}
            onChange={(e) => setDiscord(e.target.value)}
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Twitter
          </label>
          <input
            type="text"
            value={twitter}
            onChange={(e) => setTwitter(e.target.value)}
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Pronouns
          </label>
          <input
            type="text"
            value={pronouns}
            onChange={(e) => setPronouns(e.target.value)}
            placeholder="they/them"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Pronunciation
          </label>
          <input
            type="text"
            value={pronunciation}
            onChange={(e) => setPronunciation(e.target.value)}
            className="input input-sm"
          />
        </div>
      </div>
      {error && <p className="text-xs text-remove">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!displayName.trim() || saving}
          className="btn btn-sm"
        >
          {saving ? "adding…" : "add runner"}
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
