export interface Participant {
  slug: string;
  display_name: string;
  twitch: string;
  discord: string;
  twitter: string;
  pronouns: string;
  pronunciation: string;
  submission_id: string | null;
  match_confidence: string;
}

export interface Run {
  pick: number;
  scheduled: string;
  scheduled_date: string;
  game: string;
  category: string;
  estimate: string;
  estimate_seconds: number;
  platform: string;
  players: string;
  runner_display: string;
  runner_twitch: string;
  runner_discord: string;
  runner_twitter: string;
  runner_slug: string;
  note: string | null;
  layout: string | null;
  stream: string;
  stream_short: string;
  submission_id: string | null;
  category_id: string | null;
  incentives: string;
  commentator: string;
  upload_speed: string;
  pronouns: string;
  show_cam: string;
  runner_comments: string;
  slug: string;
  participants: Participant[];
}

export interface Incentive {
  scheduled: string;
  scheduled_date: string;
  game: string;
  category: string;
  stream: string;
  runner_display: string;
  runner_twitch: string;
  runner_discord: string;
  runner_slug: string;
  incentive_text: string;
  details: string;
  incentive_category: string;
  valid_for_game: string;
  incentive_estimate: string;
  needs_approval: string;
  status: string;
  submission_id: string;
  uuid: string;
  run_slug: string;
  participants: Participant[];
}

export interface RunnerDTO {
  slug: string;
  display_name: string;
  twitch: string;
  discord: string;
  twitter: string;
  pronouns: string;
  pronunciation: string;
  run_count: number;
  esa_count: number;
  first_esa: string | null;
  upcoming_runs: Run[];
}

export interface EsaRunEntry {
  game: string;
  category: string;
  count: number;
  events: string[];
}

export interface EsaFirstAppearance {
  event_slug: string;
  event_name: string;
  event_start: string;
  scheduled: string;
  game: string;
  category: string;
  estimate: string;
  stream: string;
  match: string;
}

export interface PastEsaStats {
  event_count: number;
  appearance_count: number;
  first_event: string | null;
  first_event_year: number | null;
  events: string[];
  first_appearance: EsaFirstAppearance | null;
  esa_runs: EsaRunEntry[];
  esa_game_count: number;
  esa_category_count: number;
  sources: string[];
  verified: boolean;
}

export interface RunnerStats {
  past_esa: PastEsaStats | null;
  tenure: { available: boolean; signup: string | null; years: number | null; label: string } | null;
  communities: { name: string; source: string; evidence: string }[];
  country: { code: string | null; name: string | null; source: string; confidence: string } | null;
  personal_bests: { game_count: number; category_count: number; top_games: string[] } | null;
}

export interface RunnerProfileDTO {
  slug: string;
  display_name: string;
  twitch: string;
  discord: string;
  twitter: string;
  pronouns: string;
  pronunciation: string;
  summary: {
    event_count: number;
    appearance_count: number;
    first_event: string | null;
    first_event_year: number | null;
    years_active: number | null;
    pb_count: number;
    pb_game_count: number;
    src_tenure_years: number | null;
    community_count: number;
    country_code: string | null;
    country_name: string | null;
    esa_game_count: number;
    esa_category_count: number;
  } | null;
  stats: RunnerStats | null;
  sources: { name: string; url: string }[];
  errors: string[];
  has_profile: boolean;
}

export interface BriefSidecarIncentive {
  category: string;
  description: string;
  estimate: string;
}

export interface BriefSidecarSibling {
  scheduled: string;
  game: string;
  category: string;
  estimate: string;
  stream: string;
  is_next: boolean;
}

export interface BriefSidecarCategoryInfo {
  name: string;
  wr_holder: string;
  wr_time: string;
  wr_date: string;
  records: { place: number; runner: string; time: string; date?: string }[];
}

export interface BriefSidecarSource {
  name: string;
  url: string;
}

export interface BriefSidecar {
  slug: string;
  scheduled: string;
  mode: string;
  run_meta: Record<string, unknown>;
  incentives: BriefSidecarIncentive[];
  runner_section: Record<string, unknown> | null;
  category_section: BriefSidecarCategoryInfo | null;
  game_section: Record<string, unknown> | null;
  siblings: BriefSidecarSibling[];
  sources: BriefSidecarSource[];
  confidence_flags: string[];
}

export interface BriefResponse {
  slug: string;
  prose_md: string;
  sidecar: BriefSidecar | null;
  source: string;
}

export interface BriefIndexEntry {
  slug: string;
  title: string;
  scheduled: string;
  summary_line: string;
}

export interface BriefIndexResponse {
  index_md_html: string;
  runs: BriefIndexEntry[];
}

export interface StaleInfo {
  age_hours: number | null;
  is_stale: boolean;
  is_missing: boolean;
}

export interface NewsItem {
  id: number;
  source: string; // "speedrun" | "rss"
  category: string; // "wr" | "new_run" | "news"
  source_label: string;
  title: string;
  url: string;
  summary: string;
  published_at: string | null;
  fetched_at: string;
}

function getApiBase(): string {
  if (typeof window !== "undefined") {
    // Browser — relative URLs resolve against origin automatically
    return "";
  }
  // Server (SSR) — Node.js fetch requires absolute URLs
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBase();
  const url = path.startsWith("http") ? path : `${base}${path}`;
  const res = await fetch(url, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/admin")) {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

async function fetchAdmin<T>(path: string, init?: RequestInit): Promise<T> {
  // For admin endpoints: 401 means "not admin", not "redirect to host login"
  // Caller handles the error (shows admin login form instead)
  const res = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export function login(password: string): Promise<{ ok: boolean }> {
  return fetchApi("/api/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return fetchApi("/api/logout", { method: "POST" });
}

export function getHealth(): Promise<StaleInfo> {
  return fetchApi("/api/health");
}

export function getStreams(): Promise<string[]> {
  return fetchApi("/api/streams");
}

export function getNews(limit = 50): Promise<NewsItem[]> {
  return fetchApi(`/api/news?limit=${limit}`);
}

export function getRuns(params?: {
  stream?: string;
  window?: string;
  next_hours?: number;
  marathon?: boolean;
  search?: string;
}): Promise<Run[]> {
  const q = new URLSearchParams();
  if (params?.stream) q.set("stream", params.stream);
  if (params?.window) q.set("window", params.window);
  if (params?.next_hours) q.set("next_hours", String(params.next_hours));
  if (params?.marathon) q.set("marathon", "true");
  if (params?.search) q.set("search", params.search);
  return fetchApi(`/api/runs?${q.toString()}`);
}

export function getRun(slug: string): Promise<Run> {
  return fetchApi(`/api/runs/${encodeURIComponent(slug)}`);
}

export function getIncentives(params?: {
  run_slug?: string;
  status?: string;
  category?: string;
  stream?: string;
}): Promise<Incentive[]> {
  const q = new URLSearchParams();
  if (params?.run_slug) q.set("run_slug", params.run_slug);
  if (params?.status) q.set("status", params.status);
  if (params?.category) q.set("category", params.category);
  if (params?.stream) q.set("stream", params.stream);
  return fetchApi(`/api/incentives?${q.toString()}`);
}

export function getIncentive(uuid: string): Promise<Incentive> {
  return fetchApi(`/api/incentives/${encodeURIComponent(uuid)}`);
}

export interface IncentivePatch {
  incentive_text?: string;
  details?: string;
  incentive_category?: string;
  valid_for_game?: string;
  status?: string;
  incentive_estimate?: string;
}

export function patchIncentive(uuid: string, patch: IncentivePatch): Promise<Incentive> {
  return fetchApi(`/api/incentives/${encodeURIComponent(uuid)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export interface IncentiveCreateRequest {
  run_slug: string;
  incentive_text: string;
  details?: string;
  incentive_category?: string;
  valid_for_game?: string;
  incentive_estimate?: string;
  status?: string;
}

export function createIncentive(body: IncentiveCreateRequest): Promise<Incentive> {
  return fetchApi("/api/incentives", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteIncentive(uuid: string): Promise<Incentive> {
  return fetchApi(`/api/incentives/${encodeURIComponent(uuid)}`, {
    method: "DELETE",
  });
}

export function getRunner(slug: string): Promise<RunnerDTO> {
  return fetchApi(`/api/runners/${encodeURIComponent(slug)}`);
}

export interface RunnerPBEntry {
  game: string;
  category: string;
  time: string;
  platform: string;
  verified: boolean;
  date: string | null;
  video: string;
  notes: string;
}

export interface RunnerPBDTO {
  slug: string;
  display_name: string;
  pbs: RunnerPBEntry[];
  has_pbs: boolean;
}

export function getRunnerProfile(slug: string): Promise<RunnerProfileDTO> {
  return fetchApi(`/api/runners/${encodeURIComponent(slug)}/profile`);
}

export function getRunnerPbs(slug: string): Promise<RunnerPBDTO> {
  return fetchApi(`/api/runners/${encodeURIComponent(slug)}/pbs`);
}

export function getRunnerRuns(slug: string): Promise<Run[]> {
  return fetchApi(`/api/runners/${encodeURIComponent(slug)}/runs`);
}

export function getRunners(): Promise<RunnerDTO[]> {
  return fetchApi("/api/runners");
}

export interface RunnerPatch {
  display_name?: string;
  twitch?: string;
  discord?: string;
  twitter?: string;
  pronouns?: string;
  pronunciation?: string;
}

export function adminPatchRunner(slug: string, patch: RunnerPatch): Promise<RunnerDTO> {
  return fetchAdmin(`/api/admin/runners/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export interface RunPatch {
  commentator?: string;
  pronouns?: string;
  show_cam?: string;
  runner_comments?: string;
  runner_slugs?: string[];
}

export function adminPatchRun(slug: string, patch: RunPatch): Promise<Run> {
  return fetchAdmin(`/api/admin/runs/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export interface RunCreateRequest {
  pick?: number;
  scheduled: string;
  game: string;
  category: string;
  estimate?: string;
  platform?: string;
  players?: string;
  note?: string;
  layout?: string;
  stream?: string;
  stream_short?: string;
  submission_id?: string;
  category_id?: string;
  incentives?: string;
  commentator?: string;
  upload_speed?: string;
  pronouns?: string;
  show_cam?: string;
  runner_comments?: string;
  runner_slugs?: string[];
}

export function createRun(body: RunCreateRequest): Promise<Run> {
  return fetchAdmin("/api/admin/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteRun(slug: string): Promise<{ ok: boolean; slug: string }> {
  return fetchAdmin(`/api/admin/runs/${encodeURIComponent(slug)}`, {
    method: "DELETE",
  });
}

export function getBrief(slug: string): Promise<BriefResponse> {
  return fetchApi(`/api/briefs/${encodeURIComponent(slug)}`);
}

export function getBriefIndex(shift?: string): Promise<BriefIndexResponse> {
  const q = shift ? `?shift=${encodeURIComponent(shift)}` : "";
  return fetchApi(`/api/briefs${q}`);
}

// Admin types
export interface AdminStatus {
  db_size_bytes: number;
  db_exists: boolean;
  db_healthy: boolean;
  schema_version: number;
  last_import_at: string | null;
  counts: { runs: number; incentives: number; notes: number; hosts: number; snapshots: number };
}

export interface AdminSnapshot {
  id: string;
  size_bytes: number;
  age_hours: number;
  schema_version: number;
}

export interface AdminAuditEntry {
  timestamp: string;
  action: string;
  detail: string;
}

export interface AdminRefreshResult {
  ok: boolean;
  snapshot_id: string | null;
  runs_added: number;
  runs_updated: number;
  incentives_added: number;
  incentives_updated: number;
  error: string | null;
}

export function adminLogin(password: string): Promise<{ ok: boolean }> {
  return fetchAdmin("/api/admin/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function adminLogout(): Promise<{ ok: boolean }> {
  return fetchAdmin("/api/admin/logout", { method: "POST" });
}

export function adminStatus(): Promise<AdminStatus> {
  return fetchAdmin("/api/admin/status");
}

export function adminRefresh(): Promise<AdminRefreshResult> {
  return fetchAdmin("/api/admin/refresh", { method: "POST" });
}

export function adminSnapshots(): Promise<AdminSnapshot[]> {
  return fetchAdmin("/api/admin/snapshots");
}

export function adminRestore(snapshotId: string): Promise<AdminRefreshResult> {
  return fetchAdmin("/api/admin/restore", {
    method: "POST",
    body: JSON.stringify({ snapshot_id: snapshotId }),
  });
}

export function adminAudit(limit = 50): Promise<AdminAuditEntry[]> {
  return fetchAdmin(`/api/admin/audit?limit=${limit}`);
}

// Job types
export interface JobDTO {
  id: string;
  kind: string;
  status: string;
  target: string;
  summary_json: string;
  error: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export function listJobs(params?: { kind?: string; status?: string; limit?: number }): Promise<JobDTO[]> {
  const q = new URLSearchParams();
  if (params?.kind) q.set("kind", params.kind);
  if (params?.status) q.set("status", params.status);
  if (params?.limit) q.set("limit", String(params.limit));
  return fetchAdmin(`/api/admin/jobs?${q.toString()}`);
}

export function getJob(id: string): Promise<JobDTO> {
  return fetchAdmin(`/api/admin/jobs/${encodeURIComponent(id)}`);
}

export function cancelJob(id: string): Promise<JobDTO> {
  return fetchAdmin(`/api/admin/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export function syncSchedule(): Promise<JobDTO> {
  return fetchAdmin("/api/admin/sync/schedule", { method: "POST" });
}

export function syncBriefs(params?: {
  engine?: "deterministic" | "llm";
  mode?: "scan" | "interview" | "full";
  runners?: boolean;
  slugs?: string[];
  runner?: string[];
}): Promise<JobDTO> {
  const q = new URLSearchParams();
  if (params?.engine) q.set("engine", params.engine);
  if (params?.mode) q.set("mode", params.mode);
  if (params?.runners) q.set("runners", "true");
  if (params?.slugs?.length) q.set("slugs", params.slugs.join(","));
  if (params?.runner?.length) q.set("runner", params.runner.join(","));
  const qs = q.toString() ? `?${q.toString()}` : "";
  return fetchAdmin(`/api/admin/sync/briefs${qs}`, { method: "POST" });
}

export function syncRunners(slug?: string): Promise<JobDTO> {
  const q = slug ? `?slug=${encodeURIComponent(slug)}` : "";
  return fetchAdmin(`/api/admin/sync/runners${q}`, { method: "POST" });
}

export function syncNews(): Promise<JobDTO> {
  return fetchAdmin("/api/admin/sync/news", { method: "POST" });
}

// Note types
export interface Note {
  id: number;
  run_slug: string;
  host_id: number;
  host_name: string;
  body: string;
  created_at: string;
  updated_at: string;
  is_own: boolean;
  can_edit: boolean;
}

export interface RunnerNote {
  id: number;
  runner_slug: string;
  host_id: number;
  host_name: string;
  body: string;
  created_at: string;
  updated_at: string;
  is_own: boolean;
  can_edit: boolean;
}

export interface ActiveHost {
  id: number;
  name: string;
}

export function getActiveHost(): Promise<ActiveHost> {
  return fetchApi("/api/notes/active-host");
}

export function getNotes(runSlug: string): Promise<Note[]> {
  return fetchApi(`/api/notes?run_slug=${encodeURIComponent(runSlug)}`);
}

export function createNote(runSlug: string, body: string): Promise<Note> {
  return fetchApi("/api/notes", {
    method: "POST",
    body: JSON.stringify({ run_slug: runSlug, body }),
  });
}

export function updateNote(noteId: number, body: string): Promise<Note> {
  return fetchApi(`/api/notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

export function deleteNote(noteId: number): Promise<{ ok: boolean }> {
  return fetchApi(`/api/notes/${noteId}`, { method: "DELETE" });
}

export function getRunnerNotes(runnerSlug: string): Promise<RunnerNote[]> {
  return fetchApi(`/api/runner-notes?runner_slug=${encodeURIComponent(runnerSlug)}`);
}

export function createRunnerNote(runnerSlug: string, body: string): Promise<RunnerNote> {
  return fetchApi("/api/runner-notes", {
    method: "POST",
    body: JSON.stringify({ runner_slug: runnerSlug, body }),
  });
}

export function updateRunnerNote(noteId: number, body: string): Promise<RunnerNote> {
  return fetchApi(`/api/runner-notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

export function deleteRunnerNote(noteId: number): Promise<{ ok: boolean }> {
  return fetchApi(`/api/runner-notes/${noteId}`, { method: "DELETE" });
}
