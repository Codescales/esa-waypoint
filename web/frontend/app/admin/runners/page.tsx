"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { getRunners, adminPatchRunner, type RunnerDTO, type RunnerPatch } from "@/lib/api";

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

  useEffect(() => {
    getRunners()
      .then((data) => setRunners(data))
      .finally(() => setLoading(false));
  }, []);

  function updateRunner(updated: RunnerDTO) {
    setRunners((prev) => prev.map((r) => (r.slug === updated.slug ? updated : r)));
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

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name or Twitch handle…"
        className="input input-sm mb-4 w-full max-w-sm"
      />

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th className="pb-2 pr-3 font-medium">Name</th>
                <th className="pb-2 pr-3 font-medium">Pronouns</th>
                <th className="pb-2 pr-3 font-medium">Pronunciation</th>
                <th className="pb-2 pr-3 font-medium">Twitch</th>
                <th className="pb-2 pr-3 font-medium">Discord</th>
                <th className="pb-2 pr-3 font-medium">Twitter</th>
                <th className="pb-2 pr-3 font-medium">Runs</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.slug} className="border-b border-border/50 hover:bg-surface/80">
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
