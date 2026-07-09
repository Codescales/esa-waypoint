import Link from "next/link";
import Chevron from "./Chevron";
import type { Run } from "@/lib/api";

function isSoon(scheduled: string): boolean {
  const d = new Date(scheduled);
  const now = new Date();
  return d.getTime() > now.getTime() && d.getTime() - now.getTime() < 30 * 60 * 1000;
}

function RunnerNames({ run }: { run: Run }) {
  const participants = run.participants ?? [];

  // Multi-runner: render each participant name, linked to their runner page.
  if (participants.length > 1) {
    return (
      <p className="text-xs font-medium text-right">
        {participants.map((p, i) => (
          <span key={p.slug}>
            {i > 0 && <span className="text-muted mx-0.5">&amp;</span>}
            {p.slug ? (
              <Link href={`/runner/${p.slug}`} className="hover:text-brand transition-colors">
                {p.display_name}
              </Link>
            ) : (
              <span>{p.display_name}</span>
            )}
          </span>
        ))}
      </p>
    );
  }

  // Single runner (or legacy — fall back to flat fields).
  const name = participants[0]?.display_name || run.runner_display;
  const slug = participants[0]?.slug || run.runner_slug;
  return (
    <p className="text-xs font-medium">
      {slug ? (
        <Link href={`/runner/${slug}`} className="hover:text-brand transition-colors">
          {name}
        </Link>
      ) : (
        <span>{name}</span>
      )}
    </p>
  );
}

export default function RunCard({ run }: { run: Run }) {
  const soon = isSoon(run.scheduled);

  const time = new Date(run.scheduled).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Stockholm",
  });

  return (
    <div
      className={`card p-3 transition-colors ${
        soon ? "border-upcoming/40" : "hover:border-brand/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <Link href={`/run/${run.slug}`} className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-data text-muted shrink-0 nums">{time}</span>
            {soon && (
              <span className="pill pill-now">starting soon</span>
            )}
          </div>
          <p className="font-semibold text-sm mt-1 truncate">{run.game}</p>
          <p className="text-xs text-muted truncate">{run.category}</p>
        </Link>
        <div className="text-right shrink-0">
          <RunnerNames run={run} />
          <p className="text-[11px] text-muted font-data nums">{run.estimate}</p>
        </div>
      </div>
      {run.incentives && (
        <p className="mt-1.5 text-[11px] text-muted truncate flex items-center gap-1">
          <Chevron size={10} fill="#734e9e" stroke="#734e9e" />
          {run.incentives}
        </p>
      )}
    </div>
  );
}