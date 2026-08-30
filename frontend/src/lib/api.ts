const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Resumes ────────────────────────────────────────────────
export type Resume = {
  id: string; label: string; filename: string; created_at: string;
  search_keywords: string | null; required_keywords: string[];
};
export const getResumes = () => req<Resume[]>("/resumes");
export const deleteResume = (id: string) =>
  req(`/resumes/${id}`, { method: "DELETE" });
export async function uploadResume(file: File, label: string): Promise<Resume> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("label", label);
  const res = await fetch(`${BASE}/resumes`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Jobs ───────────────────────────────────────────────────
export type WorkMode = "remote" | "hybrid" | "onsite" | null;
export type Job = {
  id: string; title: string; company: string; source: string;
  location: string; remote: boolean; work_mode: WorkMode; apply_url: string;
  fetched_at: string; posted_at: string | null;
  applied: boolean; application_id: string | null;
};
export const getJobs = (source?: string) =>
  req<Job[]>(`/jobs${source ? `?source=${source}` : ""}`);

// ── Matches ────────────────────────────────────────────────
export type Match = {
  job_id: string; resume_id: string; resume_label: string;
  job_title: string; company: string; apply_url: string; location: string | null; work_mode: WorkMode;
  posted_at: string | null; score: number;
  reasoning: string; missing_skills: string[]; selling_points: string[];
  applied: boolean; apply_status: string | null; application_id: string | null; reviewed_at: string;
};
export const getMatches = (minScore = 0) =>
  req<Match[]>(`/matches?min_score=${minScore}`);
export const applyToMatch = (jobId: string, resumeId: string) =>
  req(`/matches/${jobId}/${resumeId}/apply`, { method: "POST" });
export const generateCoverLetterForMatch = (jobId: string, resumeId: string) =>
  req<{ cover_letter: string; apply_url: string }>(`/matches/${jobId}/${resumeId}/cover-letter`, { method: "POST" });
export const markMatchApplied = (jobId: string, resumeId: string, coverLetter: string) =>
  req(`/matches/${jobId}/${resumeId}/mark-applied?cover_letter=${encodeURIComponent(coverLetter)}`, { method: "POST" });

// ── Applications ───────────────────────────────────────────
export type Application = {
  id: string; job_title: string; company: string; resume_label: string;
  match_score: number; status: string; applied_at: string; cover_letter: string;
};
export const getApplications = () => req<Application[]>("/applications");
export const updateAppStatus = (id: string, status: string, notes?: string) =>
  req(`/applications/${id}/status?status=${status}${notes ? `&notes=${notes}` : ""}`,
    { method: "PATCH" });

// ── Stats ──────────────────────────────────────────────────
export type Stats = {
  total_jobs: number; total_resumes: number; total_matches: number;
  total_applied: number; interviews: number; offers: number;
  score_threshold: number;
};
export const getStats = () => req<Stats>("/stats");

// ── Pipeline ───────────────────────────────────────────────
export const triggerPipeline = () =>
  req("/pipeline/run", { method: "POST" });

export type PipelineStatus = {
  status: "running" | "ingesting" | "matching" | "applying" | "done" | "failed";
  jobs_found: number; jobs_new: number; jobs_duped: number;
  matches_found: number; error: string | null; ran_at: string;
} | null;
export const getPipelineStatus = () => req<PipelineStatus>("/pipeline/status");
