"use client";

import { Suspense, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getRuns, getStreams, Run } from "@/lib/api";

type RunState = "upcoming" | "in_progress" | "completed" | "completed_faded";

function SchedulePageInner() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [streams, setStreams] = useState<string[]>([]);
  const [filterStream, setFilterStream] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState<number>(Date.now());
  const [showCompleted, setShowCompleted] = useState(false);

  const searchParams = useSearchParams();
  const revealCompleted = searchParams.get("show_completed") === "1";

  useEffect(() => {
    getStreams().then(setStreams);
    getRuns({ marathon: true }).then(setRuns).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const { filteredRuns, runStates, pinnedByStream } = useMemo(() => {
    let f = runs;
    if (filterStream) {
      f = f.filter((r) => r.stream === filterStream || r.stream_short === filterStream);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      f = f.filter(
        (r) =>
          r.game.toLowerCase().includes(q) ||
          r.category.toLowerCase().includes(q) ||
          r.runner_display.toLowerCase().includes(q) ||
          (r.participants ?? []).some(
            (p) =>
              p.display_name.toLowerCase().includes(q) ||
              p.twitch.toLowerCase().includes(q)
          )
      );
    }

    const states = new Map<string, RunState>();
    const completedRuns: Run[] = [];
    const activeRuns: Run[] = [];

    for (const run of f) {
      const scheduledMs = new Date(run.scheduled).getTime();
      const estimateMs = (run.estimate_seconds || 0) * 1000;
      const endsAtMs = scheduledMs + estimateMs;
      let state: RunState;

      if (estimateMs === 0) {
        if (now < scheduledMs + 2 * 3600 * 1000) {
          state = "upcoming";
        } else {
          state = "completed_faded";
        }
      } else if (now < scheduledMs) {
        state = "upcoming";
      } else if (now < endsAtMs) {
        state = "in_progress";
      } else {
        state = "completed";
      }

      states.set(run.slug, state);

      if (state === "completed" || state === "completed_faded") {
        completedRuns.push(run);
      } else {
        activeRuns.push(run);
      }
    }

    // Per-stream pinned previous run: most recent completed with estimate > 0
    const pinned = new Map<string, string>();
    const byStream = new Map<string, Run[]>();
    for (const run of completedRuns) {
      const s = run.stream || run.stream_short;
      if (!byStream.has(s)) byStream.set(s, []);
      byStream.get(s)!.push(run);
    }

    for (const [stream, streamRuns] of byStream) {
      const candidates = streamRuns.filter(
        (r) => (r.estimate_seconds || 0) > 0 && states.get(r.slug) === "completed"
      );
      if (candidates.length === 0) continue;
      candidates.sort((a, b) => {
        const aTime = new Date(a.scheduled).getTime();
        const bTime = new Date(b.scheduled).getTime();
        if (bTime !== aTime) return bTime - aTime;
        return b.pick - a.pick;
      });
      pinned.set(stream, candidates[0].slug);
    }

    const allRuns = [...activeRuns, ...completedRuns].sort(
      (a, b) => new Date(a.scheduled).getTime() - new Date(b.scheduled).getTime()
    );

    return { filteredRuns: allRuns, runStates: states, pinnedByStream: pinned };
  }, [runs, filterStream, search, now]);

  const nonPinnedCompletedCount = useMemo(() => {
    return filteredRuns.filter((r) => {
      const state = runStates.get(r.slug);
      const pinned = pinnedByStream.get(r.stream || r.stream_short) === r.slug;
      return state === "completed" && !pinned;
    }).length;
  }, [filteredRuns, runStates, pinnedByStream]);

  const visibleRuns = useMemo(() => {
    if (revealCompleted || showCompleted) return filteredRuns;
    return filteredRuns.filter((r) => {
      const state = runStates.get(r.slug);
      const pinned = pinnedByStream.get(r.stream || r.stream_short) === r.slug;
      if (state === "completed") {
        return pinned;
      }
      return true;
    });
  }, [filteredRuns, runStates, pinnedByStream, revealCompleted, showCompleted]);

  return (
    <div>
      <div className="sticky top-0 z-10 bg-background flex items-center justify-between mb-4 pb-2 pt-2">
        <h1 className="text-xl font-bold">Schedule</h1>
        <div className="text-sm text-muted font-mono">
          Now:{" "}
          {new Date(now).toLocaleTimeString("en-GB", {
            timeZone: "Europe/Stockholm",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="Search game / runner..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input flex-1 min-w-[200px]"
        />
        <select
          value={filterStream}
          onChange={(e) => setFilterStream(e.target.value)}
          className="input"
        >
          <option value="">All streams</option>
          {streams.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="card overflow-x-auto p-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th className="pb-2 pr-3 font-medium">Time</th>
                <th className="pb-2 pr-3 font-medium">Stream</th>
                <th className="pb-2 pr-3 font-medium">Game</th>
                <th className="pb-2 pr-3 font-medium">Category</th>
                <th className="pb-2 pr-3 font-medium">Runner</th>
                <th className="pb-2 pr-3 font-medium">Est</th>
              </tr>
            </thead>
            <tbody>
              {nonPinnedCompletedCount > 0 && !revealCompleted && (
                <tr
                  className="border-b border-border/50 cursor-pointer hover:bg-surface/80"
                  onClick={() => setShowCompleted((prev) => !prev)}
                >
                  <td colSpan={6} className="py-2 px-3 text-sm text-muted italic">
                    ... {nonPinnedCompletedCount} completed runs{" "}
                    <span className="text-brand font-medium">
                      {showCompleted ? "[hide]" : "[show]"}
                    </span>
                  </td>
                </tr>
              )}
              {visibleRuns.map((r) => {
                const state = runStates.get(r.slug)!;
                const pinned = pinnedByStream.get(r.stream || r.stream_short) === r.slug;
                const isCompletedState = state === "completed" || state === "completed_faded";

                let rowClass = "border-b border-border/50 ";
if (state === "in_progress") {
                  rowClass += "bg-brand/5 border-l-2 border-brand";
                } else if (isCompletedState && !revealCompleted && !pinned) {
                  rowClass += "opacity-50 text-muted";
                }

                return (
                  <tr key={r.slug} className={rowClass}>
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
                      {state === "in_progress" && (
                        <span className="pill pill-now ml-2">now playing</span>
                      )}
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
                    <td className="py-2 pr-3 text-muted max-w-[200px] truncate">
                      {r.category}
                    </td>
                    <td className="py-2 pr-3">
                      {(r.participants ?? []).length > 1 ? (
                        <span className="flex flex-wrap gap-x-1 items-center">
                          {(r.participants ?? []).map((p, i) => (
                            <span key={p.slug} className="flex items-center gap-x-1">
                              {i > 0 && <span className="text-muted text-xs">&amp;</span>}
                              {p.slug ? (
                                <Link
                                  href={`/runner/${p.slug}`}
                                  className="hover:text-brand transition-colors"
                                  title={p.twitch ? `Twitch: ${p.twitch}` : p.display_name}
                                >
                                  {p.display_name}
                                </Link>
                              ) : (
                                <span>{p.display_name}</span>
                              )}
                            </span>
                          ))}
                        </span>
                      ) : r.runner_slug ? (
                        <Link
                          href={`/runner/${r.runner_slug}`}
                          className="hover:text-brand transition-colors"
                          title={`Twitch: ${r.runner_twitch}`}
                        >
                          {r.runner_display}
                        </Link>
                      ) : (
                        <span title={`Twitch: ${r.runner_twitch}`}>
                          {r.runner_display}
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-xs text-muted">{r.estimate}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function SchedulePage() {
  return (
    <Suspense fallback={<p className="text-muted text-sm">Loading...</p>}>
      <SchedulePageInner />
    </Suspense>
  );
}
