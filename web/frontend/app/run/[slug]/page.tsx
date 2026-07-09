"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useParams } from "next/navigation";
import { getRun, getBrief, type Run, type BriefResponse } from "@/lib/api";
import RunDetail from "./RunDetail";

export default function RunPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [run, setRun] = useState<Run | null>(null);
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  useAuth();
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    Promise.all([
      getRun(slug),
      getBrief(slug).catch(() => null),
    ])
      .then(([r, b]) => {
        setRun(r);
        setBrief(b);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return <p className="text-muted text-sm mt-8">Loading...</p>;
  }

  if (error || !run) {
    return (
      <div className="text-center py-20">
        <h1 className="text-xl font-bold mb-2">Run not found</h1>
        <p className="text-muted text-sm">
          This run may have been rescheduled.{" "}
          <a href="/schedule" className="text-brand hover:underline">Browse the schedule</a>
        </p>
      </div>
    );
  }

  return <RunDetail run={run} brief={brief} />;
}
