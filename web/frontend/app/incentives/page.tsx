"use client";

import { useState, useMemo } from "react";
import { useAuth } from "@/lib/auth";
import Link from "next/link";
import { useIncentives } from "@/lib/hooks";

const STATUS_PILL: Record<string, string> = {
  Approved: "pill pill-approve",
  "In Review": "pill pill-review",
  "To-Do": "pill pill-todo",
  Removed: "pill pill-remove",
  "Needs Information": "pill pill-review",
};

export default function IncentivesPage() {
  useAuth();
  const { incentives, loading } = useIncentives({ upcoming: true });
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCategory, setFilterCategory] = useState("");

  const filtered = useMemo(() => {
    let f = incentives.filter((x) => x.status !== "Removed");
    if (filterStatus) f = f.filter((x) => x.status === filterStatus);
    if (filterCategory) f = f.filter((x) => x.incentive_category === filterCategory);
    return f;
  }, [incentives, filterStatus, filterCategory]);

  const statuses = useMemo(
    () => [...new Set(incentives.map((x) => x.status))],
    [incentives]
  );
  const categories = useMemo(
    () => [...new Set(incentives.map((x) => x.incentive_category).filter(Boolean))],
    [incentives]
  );

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
        <p className="text-sm text-muted self-center ml-auto">
          {filtered.length} of {incentives.length}
        </p>
      </div>

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
                <th className="pb-2 font-medium">Est</th>
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
                  <td className="py-2 pr-3">
                    <span className="pill pill-todo">{x.incentive_category || "—"}</span>
                  </td>
                  <td className="py-2 pr-3">
                    <span className="text-xs">{x.valid_for_game || "—"}</span>
                  </td>
                  <td className="py-2 pr-3">
                    <span className={STATUS_PILL[x.status] || "pill pill-todo"}>
                      {x.status}
                    </span>
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
