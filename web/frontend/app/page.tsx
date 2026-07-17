"use client";

import { useEffect, useState } from "react";
import { getStreams, getRuns, getBriefIndex, Run, BriefIndexResponse } from "@/lib/api";
import RunCard from "@/components/RunCard";

export default function MarathonPage() {
  const [streams, setStreams] = useState<string[]>([]);
  const [activeStream, setActiveStream] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [briefs, setBriefs] = useState<BriefIndexResponse | null>(null);

  useEffect(() => {
    getStreams().then((s) => {
      setStreams(s);
      if (s.length > 0) setActiveStream(s[0]);
    });
  }, []);

  useEffect(() => {
    if (!activeStream) return;
    setLoading(true);
    Promise.all([
      getRuns({ stream: activeStream, next_hours: 999 }),
      getBriefIndex().catch(() => null),
    ])
      .then(([r, b]) => {
        setRuns(r);
        setBriefs(b);
      })
      .finally(() => setLoading(false));
  }, [activeStream]);

  const groupedByDay = runs.reduce<Record<string, Run[]>>((acc, r) => {
    const d = new Date(r.scheduled).toLocaleDateString("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone: "Europe/Stockholm",
    });
    if (!acc[d]) acc[d] = [];
    acc[d].push(r);
    return acc;
  }, {});

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1 text-gradient inline-block">ESA Summer 2026</h1>
      <p className="text-sm text-muted mb-6">Host brief viewer</p>

      {streams.length > 0 && (
        <div className="flex gap-2 mb-6 flex-wrap">
          {streams.map((s) => (
            <button
              key={s}
              onClick={() => setActiveStream(s)}
              className={`btn btn-sm ${
                activeStream === s ? "" : "btn-b2"
              }`}
            >
              {s.replace(/^\d{4}\s*-\s*\w+\s*\(/, "").replace(/\)$/, "") || s}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupedByDay).map(([day, dayRuns]) => (
            <section key={day}>
              <h2 className="text-lg font-semibold mb-3">{day}</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {dayRuns.map((r) => (
                  <RunCard key={r.slug} run={r} />
                ))}
              </div>
            </section>
          ))}
          {runs.length === 0 && (
            <p className="text-muted text-sm">No upcoming runs found.</p>
          )}
        </div>
      )}
    </div>
  );
}
