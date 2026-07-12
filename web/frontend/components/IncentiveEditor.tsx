"use client";

import { useState } from "react";
import { Incentive, patchIncentive, deleteIncentive, type IncentivePatch } from "@/lib/api";

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

interface Props {
  incentive: Incentive;
  onUpdate: (updated: Incentive) => void;
  readOnly?: boolean;
}

export default function IncentiveEditor({ incentive, onUpdate, readOnly }: Props) {
  if (readOnly) {
    return (
      <div className="card p-4 space-y-3">
        <p className="text-sm text-foreground/80 leading-relaxed">{incentive.incentive_text}</p>
        {incentive.details && (
          <p className="text-sm text-muted leading-relaxed whitespace-pre-wrap">{incentive.details}</p>
        )}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Field label="Category">
            <span className="text-sm text-foreground/60">{incentive.incentive_category || "—"}</span>
          </Field>
          <Field label="Valid">
            <span className="text-sm text-foreground/60">{incentive.valid_for_game || "—"}</span>
          </Field>
          <Field label="Status">
            <span className="text-sm text-foreground/60">{incentive.status || "—"}</span>
          </Field>
          <Field label="Estimate">
            <span className="text-sm text-foreground/60">{incentive.incentive_estimate || "—"}</span>
          </Field>
        </div>
      </div>
    );
  }

  const [category, setCategory] = useState(incentive.incentive_category || "");
  const [valid, setValid] = useState(incentive.valid_for_game || "");
  const [status, setStatus] = useState(incentive.status || "");
  const [estimate, setEstimate] = useState(incentive.incentive_estimate || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const dirty =
    category !== (incentive.incentive_category || "") ||
    valid !== (incentive.valid_for_game || "") ||
    status !== (incentive.status || "") ||
    estimate !== (incentive.incentive_estimate || "");

  async function save() {
    setSaving(true);
    setError("");
    setSaved(false);
    const patch: IncentivePatch = {};
    if (category !== (incentive.incentive_category || ""))
      patch.incentive_category = category;
    if (valid !== (incentive.valid_for_game || "")) patch.valid_for_game = valid;
    if (status !== (incentive.status || "")) patch.status = status;
    if (estimate !== (incentive.incentive_estimate || "")) patch.incentive_estimate = estimate;

    try {
      const updated = await patchIncentive(incentive.uuid, patch);
      onUpdate(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  function reset() {
    setCategory(incentive.incentive_category || "");
    setValid(incentive.valid_for_game || "");
    setStatus(incentive.status || "");
    setEstimate(incentive.incentive_estimate || "");
  }

  return (
    <div className="card p-4 space-y-3">
      <p className="text-sm text-foreground/80 leading-relaxed">{incentive.incentive_text}</p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Field label="Category">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="input input-sm"
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>{c || "—"}</option>
            ))}
          </select>
        </Field>
        <Field label="Valid">
          <select
            value={valid}
            onChange={(e) => setValid(e.target.value)}
            className="input input-sm"
          >
            {VALID_OPTIONS.map((c) => (
              <option key={c} value={c}>{c || "—"}</option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="input input-sm"
          >
            {STATUS_OPTIONS.map((c) => (
              <option key={c} value={c}>{c || "—"}</option>
            ))}
          </select>
        </Field>
        <Field label="Estimate">
          <input
            type="text"
            value={estimate}
            onChange={(e) => setEstimate(e.target.value)}
            placeholder="+5 min"
            className="input input-sm"
          />
        </Field>
      </div>

      {error && (
        <p className="text-xs text-remove bg-remove/10 border border-remove/30 px-2 py-1 rounded">
          {error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="btn btn-sm"
        >
          {saving ? "saving…" : "save"}
        </button>
        <button
          onClick={reset}
          disabled={!dirty || saving}
          className="btn btn-sm btn-b2"
        >
          reset
        </button>
        {incentive.status !== "Removed" && (
          <button
            onClick={async () => {
              if (!confirm("Remove this incentive?")) return;
              try {
                await deleteIncentive(incentive.uuid);
                onUpdate({ ...incentive, status: "Removed" });
              } catch (e) {
                setError(String(e));
              }
            }}
            className="btn btn-sm ml-auto"
            style={{ background: "transparent", color: "var(--red)", border: "2px solid var(--red)", textShadow: "none" }}
          >
            remove
          </button>
        )}
        {saved && (
          <span className="text-xs text-approve font-medium">✓ saved</span>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] font-data font-medium text-muted uppercase tracking-wider mb-0.5">
        {label}
      </label>
      {children}
    </div>
  );
}