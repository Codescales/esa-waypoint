"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import Link from "next/link";
import { useIncentives } from "@/lib/hooks";
import RunSearchCombobox from "@/components/RunSearchCombobox";
import {
  patchIncentive,
  deleteIncentive,
  createIncentive,
  Incentive,
  IncentiveCreateRequest,
} from "@/lib/api";

const CATEGORY_OPTIONS = ["", "Reward", "Poll-Bid War", "Target"];
const VALID_OPTIONS = ["", "Yes", "No", "Needs Review"];
const STATUS_OPTIONS = [
  "",
  "To-Do",
  "In Review",
  "Needs Information",
  "Approved",
  "Removed",
];

const STATUS_PILL: Record<string, string> = {
  Approved: "pill pill-approve",
  "In Review": "pill pill-review",
  "To-Do": "pill pill-todo",
  Removed: "pill pill-remove",
  "Needs Information": "pill pill-review",
};

export default function IncentivesPage() {
  useAuth();
  const { incentives, loading, updateIncentive, removeIncentive, addIncentive } = useIncentives();
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [showRemoved, setShowRemoved] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const filtered = useMemo(() => {
    let f = incentives;
    if (!showRemoved) f = f.filter((x) => x.status !== "Removed");
    if (filterStatus) f = f.filter((x) => x.status === filterStatus);
    if (filterCategory) f = f.filter((x) => x.incentive_category === filterCategory);
    return f;
  }, [incentives, showRemoved, filterStatus, filterCategory]);

  const statuses = useMemo(
    () => [...new Set(incentives.map((x) => x.status))],
    [incentives]
  );
  const categories = useMemo(
    () => [...new Set(incentives.map((x) => x.incentive_category).filter(Boolean))],
    [incentives]
  );

  async function handleDelete(uuid: string) {
    try {
      await deleteIncentive(uuid);
      removeIncentive(uuid);
    } catch (e) {
      console.error("Delete failed", e);
    }
  }

  async function handleCreate(body: IncentiveCreateRequest) {
    const created = await createIncentive(body);
    addIncentive(created);
    setShowAddForm(false);
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Incentives</h1>

      <div className="flex flex-wrap gap-3 mb-4 items-center">
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="input input-sm"
        >
          <option value="">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="input input-sm"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={showRemoved}
            onChange={(e) => setShowRemoved(e.target.checked)}
            className="accent-brand"
          />
          Show removed
        </label>
        <p className="text-sm text-muted self-center ml-auto">
          {filtered.length} of {incentives.length}
        </p>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="btn btn-sm"
        >
          {showAddForm ? "cancel" : "new incentive"}
        </button>
      </div>

      {showAddForm && (
        <AddIncentiveForm
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
                <th className="pb-2 pr-3 font-medium">Game</th>
                <th className="pb-2 pr-3 font-medium">Incentive</th>
                <th className="pb-2 pr-3 font-medium">Category</th>
                <th className="pb-2 pr-3 font-medium">Valid</th>
                <th className="pb-2 pr-3 font-medium">Status</th>
                <th className="pb-2 pr-3 font-medium">Est</th>
                <th className="pb-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((x) => (
                <tr key={x.uuid} className="border-b border-border/50 hover:bg-surface/80">
                  <td className="py-2 pr-3">
                    <Link
                      href={`/run/${x.run_slug}`}
                      className="hover:text-brand transition-colors font-medium"
                    >
                      {x.game}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 max-w-[300px] truncate text-muted" title={x.incentive_text}>
                    {x.incentive_text}
                  </td>
                  <EditableSelectCell
                    value={x.incentive_category || ""}
                    options={CATEGORY_OPTIONS}
                    onSave={(val) => patchIncentive(x.uuid, { incentive_category: val })}
                    onUpdated={updateIncentive}
                  >
                    <span className="pill pill-todo">{x.incentive_category || "—"}</span>
                  </EditableSelectCell>
                  <EditableSelectCell
                    value={x.valid_for_game || ""}
                    options={VALID_OPTIONS}
                    onSave={(val) => patchIncentive(x.uuid, { valid_for_game: val })}
                    onUpdated={updateIncentive}
                  >
                    <span className="text-xs">{x.valid_for_game || "—"}</span>
                  </EditableSelectCell>
                  <EditableSelectCell
                    value={x.status || ""}
                    options={STATUS_OPTIONS}
                    onSave={(val) => patchIncentive(x.uuid, { status: val })}
                    onUpdated={updateIncentive}
                  >
                    <span className={STATUS_PILL[x.status] || "pill pill-todo"}>
                      {x.status}
                    </span>
                  </EditableSelectCell>
                  <EditableTextCell
                    value={x.incentive_estimate || ""}
                    onSave={(val) => patchIncentive(x.uuid, { incentive_estimate: val })}
                    onUpdated={updateIncentive}
                  >
                    <span className="text-xs text-muted">{x.incentive_estimate || "—"}</span>
                  </EditableTextCell>
                  <td className="py-2 pr-3">
                    {x.status !== "Removed" && (
                      <button
                        onClick={() => handleDelete(x.uuid)}
                        className="text-xs text-muted hover:text-remove transition-colors px-1"
                        title="Remove incentive"
                      >
                        ×
                      </button>
                    )}
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

function EditableSelectCell({
  value,
  options,
  onSave,
  onUpdated,
  children,
}: {
  value: string;
  options: string[];
  onSave: (val: string) => Promise<Incentive>;
  onUpdated: (incentive: Incentive) => void;
  children: React.ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
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
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
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
              <option key={o} value={o}>
                {o || "—"}
              </option>
            ))}
          </select>
          {error && (
            <span className="text-xs text-remove shrink-0" title={error}>
              !
            </span>
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
      onClick={() => setEditing(true)}
    >
      {children}
    </td>
  );
}

function EditableTextCell({
  value,
  onSave,
  onUpdated,
  children,
}: {
  value: string;
  onSave: (val: string) => Promise<Incentive>;
  onUpdated: (incentive: Incentive) => void;
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
            <span className="text-xs text-remove shrink-0" title={error}>
              !
            </span>
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

function AddIncentiveForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (body: IncentiveCreateRequest) => Promise<void>;
  onCancel: () => void;
}) {
  const [runSlug, setRunSlug] = useState("");
  const [text, setText] = useState("");
  const [category, setCategory] = useState("");
  const [valid, setValid] = useState("");
  const [estimate, setEstimate] = useState("");
  const [status, setStatus] = useState("To-Do");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!runSlug.trim() || !text.trim()) return;
    setSaving(true);
    setError("");
    try {
      await onSubmit({
        run_slug: runSlug.trim(),
        incentive_text: text.trim(),
        incentive_category: category || undefined,
        valid_for_game: valid || undefined,
        incentive_estimate: estimate || undefined,
        status: status || undefined,
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-4 p-4 card space-y-3"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Run *
          </label>
          <RunSearchCombobox
            value={runSlug}
            onChange={(slug) => setRunSlug(slug)}
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Incentive text *
          </label>
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            placeholder="100% completion"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Category
          </label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="input input-sm"
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c || "—"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Valid
          </label>
          <select
            value={valid}
            onChange={(e) => setValid(e.target.value)}
            className="input input-sm"
          >
            {VALID_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c || "—"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Estimate
          </label>
          <input
            type="text"
            value={estimate}
            onChange={(e) => setEstimate(e.target.value)}
            placeholder="+5 min"
            className="input input-sm"
          />
        </div>
        <div>
          <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
            Status
          </label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="input input-sm"
          >
            {STATUS_OPTIONS.filter(Boolean).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && <p className="text-xs text-remove">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!runSlug.trim() || !text.trim() || saving}
          className="btn btn-sm"
        >
          {saving ? "adding…" : "add incentive"}
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
