"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import type { Run, BriefResponse, RunnerProfileDTO, Participant } from "@/lib/api";
import { getRunnerProfile } from "@/lib/api";
import { useIncentives } from "@/lib/hooks";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import IncentiveEditor from "@/components/IncentiveEditor";
import NotesPanel from "@/components/NotesPanel";


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

function SectionDivider() {
  return <div className="sep-4 my-8 rounded-full" />;
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-lg font-bold text-foreground mb-4">{children}</h2>;
}


// ── Single participant card ───────────────────────────────────────────────────

function ParticipantCard({ participant, profile }: { participant: Participant; profile: RunnerProfileDTO | null }) {
  const name = participant.display_name;
  const initial = name ? name.charAt(0).toUpperCase() : "?";
  const pronunciation = participant.pronunciation || profile?.pronunciation || "";

  return (
    <div className="card overflow-hidden">
      {/* Header — name + pronunciation */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm shrink-0"
            style={{ background: "var(--grad)", color: "var(--off-white)" }}
            aria-hidden="true"
          >
            {initial}
          </div>
          <div>
            {participant.slug ? (
              <Link href={`/runner/${participant.slug}`} className="text-lg font-bold text-foreground leading-tight hover:text-brand transition-colors">
                {name}
              </Link>
            ) : (
              <h3 className="text-lg font-bold text-foreground leading-tight">{name}</h3>
            )}
            {pronunciation && (
              <p className="text-xs text-muted font-data italic">{pronunciation}</p>
            )}
          </div>
        </div>
      </div>

      {/* Contact details — Twitch or Discord only */}
      {(participant.twitch || participant.discord) && (
        <div className="border-t border-border">
          <table className="w-full text-sm">
            <tbody>
              {participant.twitch && (
                <tr className="border-b border-border/50">
                  <td className="px-5 py-2.5 text-muted font-medium w-24 align-middle">
                    <span className="flex items-center gap-1.5">
                      <svg className="w-4 h-4 text-brand" viewBox="0 0 24 24" fill="currentColor"><path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.428l-3 3v-3H6.857V1.714h13.714z"/></svg>
                      <span>Twitch</span>
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-foreground font-medium">{participant.twitch}</td>
                  <td className="px-5 py-2.5 text-right">
                    <a
                      href={`https://twitch.tv/${participant.twitch}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-brand hover:opacity-80 hover:underline"
                    >
                      Visit channel →
                    </a>
                  </td>
                </tr>
              )}
              {participant.discord && (
                <tr className="border-b border-border/50">
                  <td className="px-5 py-2.5 text-muted font-medium w-24">
                    <span className="flex items-center gap-1.5">
                      <svg className="w-4 h-4 text-brand" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.369a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028 14.09 14.09 0 001.226-1.994.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03z"/></svg>
                      <span>Discord</span>
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-foreground/80" colSpan={2}>{participant.discord}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


// ── RunnerSection: one card per participant ───────────────────────────────────

function RunnerSection({ run }: { run: Run }) {
  const participants = run.participants ?? [];
  const [profiles, setProfiles] = useState<Record<string, RunnerProfileDTO>>({});

  useEffect(() => {
    const toFetch = participants.filter((p) => p.slug);
    toFetch.forEach((p) => {
      getRunnerProfile(p.slug)
        .then((profile) => {
          if (profile) setProfiles((prev) => ({ ...prev, [p.slug]: profile }));
        })
        .catch(() => {});
    });
  }, [run.slug]);

  // Fallback for legacy runs with no participants array
  if (participants.length === 0) {
    const fallback: Participant = {
        slug: run.runner_slug,
        display_name: run.runner_display,
        twitch: run.runner_twitch,
        discord: run.runner_discord,
        twitter: run.runner_twitter,
        pronouns: run.pronouns,
        pronunciation: "",
        submission_id: run.submission_id,
        match_confidence: "",
      };
    return (
      <>
        <ParticipantCard participant={fallback} profile={profiles[run.runner_slug] ?? null} />
        {run.commentator && (
          <div className="mt-3 card px-5 py-3 bg-surface/30">
            <span className="text-xs text-muted font-data font-medium">Commentator</span>
            <span className="ml-2 text-sm text-foreground/80">{run.commentator}</span>
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <div className={participants.length > 1 ? "space-y-3" : ""}>
        {participants.map((p) => (
          <ParticipantCard key={p.slug || p.display_name} participant={p} profile={profiles[p.slug] ?? null} />
        ))}
      </div>
      {run.commentator && (
        <div className="mt-3 card px-5 py-3 bg-surface/30">
          <span className="text-xs text-muted font-data font-medium">Commentator</span>
          <span className="ml-2 text-sm text-foreground/80">{run.commentator}</span>
        </div>
      )}
    </>
  );
}


// ── Main RunDetail component ──────────────────────────────────────────────────

interface Props {
  run: Run;
  brief: BriefResponse | null;
}

export default function RunDetail({ run, brief }: Props) {
  const sidecar = brief?.sidecar;
  const { incentives, updateIncentive } = useIncentives(run.slug);

  return (
    <div className="max-w-3xl mx-auto">

      {/* ── Back link ── */}
      <Link href="/schedule" className="inline-flex items-center text-sm text-muted hover:text-foreground mb-6 transition-colors">
        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to schedule
      </Link>

      {/* ── Header ── */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground leading-tight">{run.game}</h1>
        <p className="text-lg text-muted mt-1">{run.category}</p>
        <div className="flex flex-wrap items-center gap-3 mt-3 text-sm">
          <span className="inline-flex items-center gap-1.5 text-foreground font-medium">
            <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {timeStr(run.scheduled)}
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted">
            <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            {run.stream}
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted font-data nums">
            est {run.estimate}
          </span>
          {run.platform && (
            <span className="text-muted">{run.platform}</span>
          )}
        </div>
      </div>

      {/* ── Runner card(s) ── */}
      <div className="mb-8">
        <RunnerSection run={run} />
      </div>

      {/* ── Brief prose ── */}
      {brief ? (
        <div className="prose prose-sm max-w-none prose-headings:text-foreground prose-headings:font-bold prose-h2:text-lg prose-h2:mt-8 prose-h2:mb-3 prose-h3:text-base prose-h3:mt-6 prose-h3:mb-2 prose-p:text-muted prose-p:leading-relaxed prose-a:text-brand prose-a:no-underline hover:prose-a:underline prose-strong:text-foreground prose-li:text-muted prose-li:leading-relaxed">
          <Markdown remarkPlugins={[remarkGfm]}>{brief.prose_md}</Markdown>
        </div>
      ) : (
        <div className="surface-grad-15 p-5 text-center rounded-lg">
          <p className="text-sm text-off-white font-medium">No brief generated yet</p>
          <p className="text-xs text-yellow mt-1">Ask the operator to run <code className="text-yellow bg-black/30 px-1 rounded">/brief</code></p>
        </div>
      )}

      {/* ── Sidecar structured data ── */}
      {sidecar && (
        <>
          {/* Sibling runs */}
          {sidecar.siblings.length > 0 && (
            <>
              <SectionDivider />
              <section>
                <SectionHeading>Sibling Runs</SectionHeading>
                <div className="space-y-2">
                  {sidecar.siblings.map((sib, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-3 p-3 rounded-lg ${
                        sib.is_next
                          ? "border border-brand bg-brand/5"
                          : "card"
                      }`}
                    >
                      {sib.is_next && (
                        <span className="pill pill-next shrink-0">next</span>
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{sib.game}</p>
                        <p className="text-xs text-muted">{sib.category}</p>
                      </div>
                      <div className="text-right shrink-0 ml-auto">
                        <p className="text-xs text-muted font-data">{sib.scheduled}</p>
                        <p className="text-xs text-muted font-data">{sib.stream}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}

          {/* Sources */}
          {sidecar.sources.length > 0 && (
            <>
              <SectionDivider />
              <section>
                <SectionHeading>Sources</SectionHeading>
                <ul className="space-y-1">
                  {sidecar.sources.map((s, i) => (
                    <li key={i}>
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sm text-brand hover:opacity-80 hover:underline">
                          {s.name}
                        </a>
                      ) : (
                        <span className="text-sm text-muted">{s.name}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}

          {/* Confidence flags */}
          {sidecar.confidence_flags.length > 0 && (
            <>
              <SectionDivider />
              <section
                className="rounded-lg p-5"
                style={{ background: "rgba(253,187,28,.08)", border: "1px solid rgba(253,187,28,.4)" }}
              >
                <h3 className="text-sm font-bold text-yellow mb-2">Confidence Flags</h3>
                <ul className="space-y-1">
                  {sidecar.confidence_flags.map((f, i) => (
                    <li key={i} className="text-sm text-yellow flex gap-2">
                      <span className="shrink-0">⚠</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </>
      )}

      {/* ── Incentives ── */}
      <SectionDivider />
      <section>
        <SectionHeading>Incentives</SectionHeading>
        {incentives.length > 0 ? (
          <div className="space-y-3">
            {incentives.map((x) => (
              <IncentiveEditor
                key={x.uuid}
                incentive={x}
                onUpdate={updateIncentive}
                readOnly
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted italic">No incentives for this run.</p>
        )}
      </section>

      {/* ── Notes ── */}
      <SectionDivider />
      <section>
        <NotesPanel runSlug={run.slug} />
      </section>

      {/* ── Page footer ── */}
      <div className="mt-10 pt-6 border-t border-border">
        <Link href="/schedule" className="text-sm text-muted hover:text-foreground transition-colors">
          ← Back to schedule
        </Link>
      </div>

    </div>
  );
}
