"use client";

import { useState, useMemo, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import Link from "next/link";
import { useIncentives } from "@/lib/hooks";
import { getStreams } from "@/lib/api";

type SortKey = "game" | "time";

export default function IncentivesPage() {
  useAuth();
  const { incentives, loading } = useIncentives({ upcoming: true });
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterStream, setFilterStream] = useState("");
  const [streams, setStreams] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("time");

  useEffect(() => {
    getStreams().then(setStreams);
  }, []);

  const filtered = useMemo(() => {
    let f = incentives.filter((x) => x.status !== "Removed");
    if (filterStatus) f = f.filter((x) => x.status === filterStatus);
    if (filterCategory) f = f.filter((x) => x.incentive_category === filterCategory);
    if (filterStream) f = f.filter((x) => x.stream === filterStream);
    return f;
  }, [incentives, filterStatus, filterCategory, filterStream]);

  const sorted = useMemo(() => {
    const f = [...filtered];
    if (sortKey === "game") {
      f.sort((a, b) => a.game.localeCompare(b.game));
    } else {
      f.sort((a, b) => new Date(a.scheduled).getTime() - new Date(b.scheduled).getTime());
    }
    return f;
  }, [filtered, sortKey]);

  const statuses = useMemo(
    () => [...new Set(incentives.map((x) => x.status))],
    [incentives]
  );
  const categories = useMemo(
    () => [...new Set(incentives.map((x) => x.incentive_category).filter(Boolean))],
    [incentives]
  );

  function toggleSort(key: SortKey) {
    setSortKey((prev) => (prev === key ? key : key));
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Incentives</h1>
      <p className="text-sm text-muted mb-4">
        Upcoming incentives — read-only view.{" "}
        <Link href="/admin/incentives" className="text-brand hover:underline">
          Admin view
        </Link>{" "}
        for full editing.
      </p>

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
        <select
          value={filterStream}
          onChange={(e) => setFilterStream(e.target.value)}
          className="input input-sm"
        >
          <option value="">All streams</option>
          {streams.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <p className="text-sm text-muted self-center ml-auto">
          {sorted.length} of {incentives.length}
        </p>
      </div>

      {loading ? (
        <p className="text-muted text-sm">Loading...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th className="pb-2 pr-3 font-medium">Time</th>
                <th className="pb-2 pr-3 font-medium">Stream</th>
                <th
                  className="pb-2 pr-3 font-medium cursor-pointer hover:text-brand select-none"
                  onClick={() => toggleSort("game")}
                >
                  Game{sortKey === "game" ? " \u25B2" : ""}
                </th>
                <th className="pb-2 pr-3 font-medium">Incentive</th>
                <th className="pb-2 pr-3 font-medium">Details</th>
                <th className="pb-2 pr-3 font-medium">Category</th>
                <th className="pb-2 font-medium">Est</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((x) => (
                <tr key={x.uuid} className="border-b border-border/50 hover:bg-surface/80">
                  <td className="py-2 pr-3 font-mono text-xs whitespace-nowrap">
                    {new Date(x.scheduled).toLocaleDateString("en-GB", {
                      day: "2-digit",
                      month: "2-digit",
                      timeZone: "Europe/Stockholm",
                    })}{" "}
                    {new Date(x.scheduled).toLocaleTimeString("en-GB", {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: "Europe/Stockholm",
                    })}
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted">{x.stream}</td>
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
                  <td className="py-2 pr-3 max-w-[200px] truncate text-muted" title={x.details || ""}>
                    {x.details || "—"}
                  </td>
                  <td className="py-2 pr-3">
                    <span className="pill pill-todo">{x.incentive_category || "—"}</span>
                  </td>
                  <td className="py-2">
                    <span className="text-xs text-muted">{x.incentive_estimate || "—"}</span>
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
