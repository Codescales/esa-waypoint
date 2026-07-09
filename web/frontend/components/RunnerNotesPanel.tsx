"use client";

import { useEffect, useState, FormEvent } from "react";
import {
  getRunnerNotes,
  createRunnerNote,
  updateRunnerNote,
  deleteRunnerNote,
  getActiveHost,
  type RunnerNote,
  type ActiveHost,
} from "@/lib/api";

function timeStr(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Stockholm",
  });
}

interface Props {
  runnerSlug: string;
}

export default function RunnerNotesPanel({ runnerSlug }: Props) {
  const [notes, setNotes] = useState<RunnerNote[]>([]);
  const [activeHost, setActiveHost] = useState<ActiveHost | null>(null);
  const [loading, setLoading] = useState(true);
  const [newBody, setNewBody] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [n, h] = await Promise.all([getRunnerNotes(runnerSlug), getActiveHost()]);
      setNotes(n);
      setActiveHost(h);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [runnerSlug]);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    const body = newBody.trim();
    if (!body) return;
    setSaving(true);
    setError("");
    try {
      const note = await createRunnerNote(runnerSlug, body);
      setNotes((prev) => [note, ...prev]);
      setNewBody("");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveEdit(noteId: number) {
    const body = editBody.trim();
    if (!body) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateRunnerNote(noteId, body);
      setNotes((prev) => prev.map((n) => (n.id === noteId ? updated : n)));
      setEditingId(null);
      setEditBody("");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(noteId: number) {
    if (!confirm("Delete this note?")) return;
    setError("");
    try {
      await deleteRunnerNote(noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-foreground">Notes</h2>
        {activeHost && (
          <span className="text-xs text-muted">
            Posting as <span className="font-medium text-foreground">{activeHost.name}</span>
          </span>
        )}
      </div>

      {/* New note form */}
      <form onSubmit={handleAdd} className="space-y-2">
        <textarea
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          placeholder="Add a note for this runner..."
          rows={3}
          className="input"
        />
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={!newBody.trim() || saving}
            className="btn btn-sm"
          >
            {saving ? "posting…" : "post note"}
          </button>
          <span className="text-xs text-muted">
            {newBody.length}/10000
          </span>
        </div>
      </form>

      {error && (
        <p className="text-xs text-remove bg-remove/10 border border-remove/30 px-2 py-1 rounded">
          {error}
        </p>
      )}

      {/* List */}
      {loading ? (
        <p className="text-sm text-muted">Loading...</p>
      ) : notes.length === 0 ? (
        <p className="text-sm text-muted italic">No notes yet.</p>
      ) : (
        <ul className="space-y-3">
          {notes.map((n) => (
            <li key={n.id} className="card p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-semibold text-sm text-foreground truncate">
                    {n.host_name}
                  </span>
                  <span className="text-xs text-muted">·</span>
                  <span className="text-xs text-muted shrink-0">
                    {timeStr(n.created_at)}
                  </span>
                  {n.updated_at !== n.created_at && (
                    <span className="text-xs text-muted italic">
                      (edited {timeStr(n.updated_at)})
                    </span>
                  )}
                </div>
                {n.can_edit && (
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => {
                        setEditingId(n.id);
                        setEditBody(n.body);
                      }}
                      className="text-xs text-muted hover:text-foreground"
                    >
                      edit
                    </button>
                    <button
                      onClick={() => handleDelete(n.id)}
                      className="text-xs text-remove hover:opacity-80"
                    >
                      delete
                    </button>
                  </div>
                )}
              </div>

              {editingId === n.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editBody}
                    onChange={(e) => setEditBody(e.target.value)}
                    rows={3}
                    className="input"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSaveEdit(n.id)}
                      disabled={!editBody.trim() || saving}
                      className="btn btn-sm"
                    >
                      {saving ? "saving…" : "save"}
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(null);
                        setEditBody("");
                      }}
                      className="text-sm text-muted hover:text-foreground"
                    >
                      cancel
                    </button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-foreground/80 whitespace-pre-wrap">{n.body}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}