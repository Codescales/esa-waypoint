"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { getRunner, getRunnerProfile, getRunnerPbs, getRunnerRuns, adminPatchRunner, type RunnerDTO, type RunnerProfileDTO, type RunnerPBDTO, type Run, type PastEsaStats } from "@/lib/api";
import RunnerNotesPanel from "@/components/RunnerNotesPanel";
import AdminRunnerEditor from "@/components/AdminRunnerEditor";

function timeStr(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Stockholm",
  });
}

function EsaHistory({ past }: { past: PastEsaStats }) {
  return (
    <div className="mb-8">
      <h2 className="text-lg font-bold text-foreground mb-4">ESA History</h2>
      {past.events.length > 0 && (
        <div className="card p-4 mb-3">
          <p className="text-[10px] text-muted font-data font-medium uppercase tracking-wider mb-2">
            Events Attended ({past.event_count})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {past.events.map((ev) => (
              <span key={ev} className="pill pill-todo text-[11px]">{ev}</span>
            ))}
          </div>
        </div>
      )}
      {past.first_appearance && (
        <div className="card p-4 mb-3">
          <p className="text-[10px] text-muted font-data font-medium uppercase tracking-wider mb-2">First Appearance</p>
          <p className="text-sm font-semibold text-foreground">{past.first_appearance.game}</p>
          <p className="text-xs text-muted">{past.first_appearance.category} · {past.first_appearance.estimate}</p>
          <p className="text-xs text-muted mt-0.5">{past.first_appearance.event_name}</p>
        </div>
      )}
      {past.esa_runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border text-left text-[10px] text-muted font-data font-medium uppercase tracking-wider">
                <th className="pb-2 pr-3">Game</th>
                <th className="pb-2 pr-3">Category</th>
                <th className="pb-2 pr-3">Times</th>
                <th className="pb-2">Events</th>
              </tr>
            </thead>
            <tbody>
              {past.esa_runs.map((r, i) => (
                <tr key={i} className="border-b border-border/50 text-foreground/80">
                  <td className="py-2 pr-3 font-medium">{r.game}</td>
                  <td className="py-2 pr-3 text-muted">{r.category}</td>
                  <td className="py-2 pr-3 nums text-center">{r.count}</td>
                  <td className="py-2 text-xs text-muted">{r.events.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface Props {
  params: Promise<{ slug: string }>;
}

export default function RunnerPage({ params }: Props) {
  const [slug, setSlug] = useState<string | null>(null);
  const [runner, setRunner] = useState<RunnerDTO | null>(null);
  const [profile, setProfile] = useState<RunnerProfileDTO | null>(null);
  const [pbs, setPbs] = useState<RunnerPBDTO | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);

  useEffect(() => {
    params.then((p) => setSlug(p.slug));
  }, [params]);

  useEffect(() => {
    if (!slug) return;
    getRunner(slug).then(setRunner);
    getRunnerProfile(slug).then(setProfile).catch(() => {});
    getRunnerPbs(slug).then(setPbs).catch(() => {});
    getRunnerRuns(slug).then(setRuns);
  }, [slug]);

  if (!runner) {
    return <p className="text-muted text-sm mt-8">Loading...</p>;
  }

  return (
    <div className="max-w-3xl mx-auto">
      <a href="/schedule" className="inline-flex items-center text-sm text-muted hover:text-foreground mb-6 transition-colors lowercase">
        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to schedule
      </a>

      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center font-bold text-lg shrink-0"
            style={{ background: "var(--grad)", color: "var(--off-white)" }}
            aria-hidden="true"
          >
            {runner.display_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground leading-tight">{runner.display_name}</h1>
            {runner.pronunciation && (
              <p className="text-sm text-muted font-data italic mt-0.5">{runner.pronunciation}</p>
            )}
            {runner.pronouns && (
              <span className="pill pill-todo ml-1">{runner.pronouns}</span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-4 mt-3 text-sm">
          {runner.twitch && (
            <a href={`https://twitch.tv/${runner.twitch}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-brand hover:opacity-80">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.428l-3 3v-3H6.857V1.714h13.714z"/></svg>
              <span>{runner.twitch}</span>
            </a>
          )}
          {runner.discord && (
            <span className="inline-flex items-center gap-1.5 text-muted">
              <svg className="w-4 h-4 text-brand" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.369a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028 14.09 14.09 0 001.226-1.994.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03z"/></svg>
              <span>{runner.discord}</span>
            </span>
          )}
          {runner.twitter && (
            <a href={`https://twitter.com/${runner.twitter}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sky-600 hover:opacity-80">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              <span>@{runner.twitter}</span>
            </a>
          )}
        </div>

        <AdminRunnerEditor runner={runner} onUpdated={setRunner} />

        {profile?.has_profile && profile.summary && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {[
              ["ESA Events", profile.summary.event_count],
              ["ESA Runs", profile.summary.appearance_count],
              ["First ESA", profile.summary.first_event_year ?? "—"],
              ["Games at ESA", profile.summary.esa_game_count],
              ["Games on SRC", profile.summary.pb_game_count],
              ["On SRC", `${profile.summary.src_tenure_years ?? "—"}y`],
            ].map(([label, value]) => (
              <div key={label as string} className="card p-3">
                <p className="text-[10px] text-muted font-data font-medium uppercase tracking-wider">{label as string}</p>
                <p className="text-lg font-bold text-foreground nums">{value as React.ReactNode}</p>
              </div>
            ))}
            {profile.summary.country_name && (
              <div className="card p-3 col-span-2">
                <p className="text-[10px] text-muted font-data font-medium uppercase tracking-wider">Country</p>
                <p className="text-lg font-bold text-foreground">{profile.summary.country_name} <span className="text-[10px] text-muted font-normal">(unverified)</span></p>
              </div>
            )}
          </div>
        )}

        <p className="text-sm text-muted mt-2">
          {runner.run_count} run{runner.run_count !== 1 ? "s" : ""}
          {runner.esa_count > 0 && <> · {runner.esa_count} ESA{runner.esa_count !== 1 ? "s" : ""}</>}
          {runner.first_esa && <> · First ESA: {runner.first_esa}</>}
        </p>
      </div>

      {profile?.has_profile && profile.stats?.past_esa && profile.stats.past_esa.verified && (
        <EsaHistory past={profile.stats.past_esa} />
      )}

      {runs.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-bold text-foreground mb-4">Upcoming Runs</h2>
          <div className="space-y-2">
            {runs.map((r) => (
              <Link key={r.slug} href={`/run/${r.slug}`} className="block p-3 card hover:border-brand/40 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-sm truncate">{r.game}</p>
                    <p className="text-xs text-muted truncate">{r.category}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-muted">{timeStr(r.scheduled)}</p>
                    <p className="text-[11px] text-muted font-data">{r.stream}</p>
                  </div>
                </div>
                {r.incentives && (
                  <p className="mt-1.5 text-[11px] text-muted truncate">{r.incentives}</p>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}

      {runs.length === 0 && (
        <div className="card bg-surface/30 p-5 text-center mb-8">
          <p className="text-sm text-muted">No upcoming runs scheduled.</p>
        </div>
      )}

      {pbs && (
        <div className="mb-8">
          <h2 className="text-lg font-bold text-foreground mb-4">Personal Bests</h2>
          {!pbs.has_pbs ? (
            <div className="card bg-surface/30 p-5 text-center">
              <p className="text-sm text-muted">No PB data yet.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-border text-left text-[10px] text-muted font-data font-medium uppercase tracking-wider">
                    <th className="pb-2 pr-3">Game</th>
                    <th className="pb-2 pr-3">Category</th>
                    <th className="pb-2 pr-3">Time</th>
                    <th className="pb-2 pr-3">Platform</th>
                    <th className="pb-2 pr-3">Verified</th>
                    <th className="pb-2 pr-3">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {pbs.pbs.map((pb, i) => (
                    <tr key={i} className="border-b border-border/50 text-foreground/80">
                      <td className="py-2 pr-3 font-medium">{pb.game}</td>
                      <td className="py-2 pr-3">{pb.category}</td>
                      <td className="py-2 pr-3 whitespace-nowrap nums text-dark-yellow">{pb.time}</td>
                      <td className="py-2 pr-3">{pb.platform}</td>
                      <td className="py-2 pr-3">{pb.verified ? "Yes" : "No"}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">{pb.date ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <RunnerNotesPanel runnerSlug={slug!} />
    </div>
  );
}
