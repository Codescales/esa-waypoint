"use client";

import { useState } from "react";
import { adminPatchRunner, type RunnerDTO } from "@/lib/api";

interface Props {
  runner: RunnerDTO;
  onUpdated: (runner: RunnerDTO) => void;
}

export default function AdminRunnerEditor({ runner, onUpdated }: Props) {
  const [editing, setEditing] = useState(false);
  const [pronunciation, setPronunciation] = useState(runner.pronunciation);
  const [twitch, setTwitch] = useState(runner.twitch);
  const [discord, setDiscord] = useState(runner.discord);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const updated = await adminPatchRunner(runner.slug, {
        pronunciation: pronunciation || "",
        twitch: twitch || "",
        discord: discord || "",
      });
      onUpdated(updated);
      setEditing(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <button onClick={() => setEditing(true)} className="btn btn-sm btn-b2 text-[10px]">
        edit runner
      </button>
    );
  }

  return (
    <div className="card p-4 mt-3 space-y-3">
      <p className="text-xs font-bold text-foreground">Edit Runner</p>
      <div>
        <label className="block text-[10px] text-muted font-data mb-0.5">Pronunciation</label>
        <input type="text" value={pronunciation} onChange={(e) => setPronunciation(e.target.value)} className="input input-sm" placeholder="e.g. THAIR-ix-er" />
      </div>
      <div>
        <label className="block text-[10px] text-muted font-data mb-0.5">Twitch</label>
        <input type="text" value={twitch} onChange={(e) => setTwitch(e.target.value)} className="input input-sm" />
      </div>
      <div>
        <label className="block text-[10px] text-muted font-data mb-0.5">Discord</label>
        <input type="text" value={discord} onChange={(e) => setDiscord(e.target.value)} className="input input-sm" />
      </div>
      {error && <p className="text-xs text-remove">{error}</p>}
      <div className="flex gap-2">
        <button onClick={handleSave} disabled={saving} className="btn btn-sm">
          {saving ? "saving..." : "save"}
        </button>
        <button onClick={() => setEditing(false)} className="btn btn-sm btn-b2">cancel</button>
      </div>
    </div>
  );
}
