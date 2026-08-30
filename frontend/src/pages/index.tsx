"use client";
import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  getStats, getMatches, getApplications, getResumes, getJobs,
  uploadResume, deleteResume, triggerPipeline, updateAppStatus, applyToMatch,
  type Stats, type Match, type Application, type Resume, type Job,
} from "../lib/api";

// ── Score badge ────────────────────────────────────────────
function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 85 ? "text-teal border-teal/40 bg-teal/10" :
    pct >= 70 ? "text-sky border-sky/40 bg-sky/10" :
    pct >= 50 ? "text-amber border-amber/40 bg-amber/10" :
               "text-muted border-border bg-panel";
  return (
    <span className={`font-mono text-xs px-2 py-0.5 rounded border ${color}`}>
      {pct}%
    </span>
  );
}

// ── Status pill ────────────────────────────────────────────
function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    applied:   "text-teal  bg-teal/10  border-teal/30",
    interview: "text-amber bg-amber/10 border-amber/30",
    offer:     "text-teal  bg-teal/20  border-teal/50",
    rejected:  "text-rose  bg-rose/10  border-rose/30",
    failed:    "text-rose  bg-rose/10  border-rose/30",
    ghosted:   "text-muted bg-panel    border-border",
    skipped:   "text-muted bg-panel    border-border",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded border capitalize ${map[status] ?? "text-muted border-border"}`}>
      {status}
    </span>
  );
}

// ── Source tag ─────────────────────────────────────────────
function SourceTag({ source }: { source: string }) {
  const colors: Record<string, string> = {
    adzuna:     "text-sky   border-sky/30",
    remotive:   "text-teal  border-teal/30",
    greenhouse: "text-amber border-amber/30",
    lever:      "text-rose  border-rose/30",
  };
  return (
    <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${colors[source] ?? "text-muted border-border"}`}>
      {source}
    </span>
  );
}

// ── Stat card ──────────────────────────────────────────────
function StatCard({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="border border-border bg-surface px-5 py-4 flex flex-col gap-1 min-w-[110px]">
      <span className={`font-mono text-2xl font-bold ${accent ?? "text-text"}`}>{value}</span>
      <span className="text-xs text-muted">{label}</span>
    </div>
  );
}

// ── Sidebar nav item ───────────────────────────────────────
function NavItem({ icon, label, active, onClick, badge }: {
  icon: string; label: string; active: boolean; onClick: () => void; badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors relative
        ${active
          ? "bg-teal/10 text-teal border-r-2 border-teal"
          : "text-muted hover:text-text hover:bg-panel/60"}`}
    >
      <span className="text-base">{icon}</span>
      <span className="flex-1">{label}</span>
      {badge != null && badge > 0 && (
        <span className="text-xs font-mono bg-teal/20 text-teal px-1.5 py-0.5 rounded">{badge}</span>
      )}
    </button>
  );
}

// ── Detail drawer ──────────────────────────────────────────
function MatchDrawer({ match, onClose, onApplied }: { match: Match; onClose: () => void; onApplied: () => void }) {
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");

  async function handleApply() {
    setApplying(true);
    setError("");
    try {
      await applyToMatch(match.job_id, match.resume_id);
      onApplied();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/70" onClick={onClose} />
      <div className="relative w-[520px] h-full bg-surface border-l border-border overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-surface z-10">
          <div>
            <div className="font-semibold text-text">{match.job_title}</div>
            <div className="text-sm text-muted">{match.company}</div>
          </div>
          <div className="flex items-center gap-3">
            <ScoreBadge score={match.score} />
            <button onClick={onClose} className="text-muted hover:text-text text-xl leading-none">×</button>
          </div>
        </div>

        <div className="px-6 py-5 flex flex-col gap-6">
          {/* Resume used */}
          <section>
            <div className="text-xs text-muted mb-2">Resume matched</div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm bg-teal/10 border border-teal/30 text-teal px-3 py-1 rounded">
                {match.resume_label}
              </span>
              {match.applied ? (
                <StatusPill status={match.apply_status ?? "applied"} />
              ) : (
                <button
                  onClick={handleApply}
                  disabled={applying}
                  className="text-xs bg-teal text-ink font-semibold px-3 py-1.5 rounded hover:bg-teal/90 disabled:opacity-50 transition-colors"
                >
                  {applying ? "Applying…" : "Apply"}
                </button>
              )}
            </div>
            {error && <div className="text-xs text-rose mt-2">{error}</div>}
          </section>

          {/* Claude reasoning */}
          <section>
            <div className="text-xs text-muted mb-2">Claude's assessment</div>
            <p className="text-sm text-text leading-relaxed bg-panel border border-border rounded p-4">
              {match.reasoning}
            </p>
          </section>

          {/* Selling points */}
          {match.selling_points?.length > 0 && (
            <section>
              <div className="text-xs text-muted mb-2">Selling points used</div>
              <ul className="flex flex-col gap-1.5">
                {match.selling_points.map((p, i) => (
                  <li key={i} className="flex gap-2 text-sm text-text">
                    <span className="text-teal mt-0.5">✓</span> {p}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Missing skills */}
          {match.missing_skills?.length > 0 && (
            <section>
              <div className="text-xs text-muted mb-2">Gaps identified</div>
              <div className="flex flex-wrap gap-2">
                {match.missing_skills.map((s, i) => (
                  <span key={i} className="text-xs px-2 py-1 bg-rose/10 border border-rose/30 text-rose rounded">
                    {s}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Cover letter drawer ────────────────────────────────────
function CoverDrawer({ app, onClose }: { app: Application; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/70" onClick={onClose} />
      <div className="relative w-[560px] h-full bg-surface border-l border-border overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-surface">
          <div>
            <div className="font-semibold text-text">{app.job_title}</div>
            <div className="text-sm text-muted">{app.company} · {app.resume_label}</div>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text text-xl">×</button>
        </div>
        <div className="px-6 py-5">
          <div className="text-xs text-muted mb-3">Cover letter sent</div>
          <pre className="text-sm text-text leading-relaxed whitespace-pre-wrap font-sans bg-panel border border-border rounded p-5">
            {app.cover_letter || "No cover letter on record."}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ── Upload modal ───────────────────────────────────────────
function UploadModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [label, setLabel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit() {
    if (!file || !label.trim()) { setError("Label and file are required."); return; }
    setLoading(true);
    try {
      await uploadResume(file, label.trim());
      onDone();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-ink/80" onClick={onClose} />
      <div className="relative bg-surface border border-border rounded w-[420px] p-6 flex flex-col gap-4">
        <div className="text-sm font-semibold text-text">Upload resume</div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Label (e.g. "Backend Engineer")</label>
          <input
            className="bg-panel border border-border text-text text-sm rounded px-3 py-2 outline-none focus:border-teal/60 transition-colors"
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="Backend Engineer"
          />
        </div>

        <div
          className="border-2 border-dashed border-border rounded p-6 flex flex-col items-center gap-2 cursor-pointer hover:border-teal/40 transition-colors"
          onClick={() => inputRef.current?.click()}
        >
          <span className="text-2xl">📄</span>
          <span className="text-sm text-muted">
            {file ? file.name : "Click to select PDF or DOCX"}
          </span>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt"
            className="hidden"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {error && <div className="text-xs text-rose">{error}</div>}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="text-sm text-muted px-4 py-2 hover:text-text transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="text-sm bg-teal text-ink font-semibold px-4 py-2 rounded hover:bg-teal/90 disabled:opacity-50 transition-colors"
          >
            {loading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Tab: Dashboard ─────────────────────────────────────────
function DashboardTab({ stats }: { stats: Stats | null }) {
  const funnelSteps = [
    { label: "Jobs fetched",  value: stats?.total_jobs ?? 0,    color: "bg-sky/20   border-sky/30",   text: "text-sky" },
    { label: "Matches ≥70%",  value: stats?.total_matches ?? 0, color: "bg-teal/20  border-teal/30",  text: "text-teal" },
    { label: "Applied",       value: stats?.total_applied ?? 0, color: "bg-teal/30  border-teal/50",  text: "text-teal" },
    { label: "Interviews",    value: stats?.interviews ?? 0,     color: "bg-amber/20 border-amber/30", text: "text-amber" },
    { label: "Offers",        value: stats?.offers ?? 0,         color: "bg-teal/40  border-teal/60",  text: "text-teal" },
  ];

  const max = Math.max(...funnelSteps.map(s => s.value), 1);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h2 className="text-sm font-semibold text-text mb-4">Pipeline funnel</h2>
        <div className="flex flex-col gap-2">
          {funnelSteps.map((step, i) => {
            const width = Math.max((step.value / max) * 100, 4);
            return (
              <div key={i} className="flex items-center gap-4">
                <div className="w-28 text-xs text-muted text-right shrink-0">{step.label}</div>
                <div className="flex-1 bg-panel rounded h-8 overflow-hidden border border-border">
                  <div
                    className={`h-full border-r ${step.color} transition-all duration-500 flex items-center pl-3`}
                    style={{ width: `${width}%` }}
                  >
                    <span className={`font-mono text-sm font-bold ${step.text}`}>{step.value}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-text mb-4">At a glance</h2>
        <div className="grid grid-cols-2 gap-4 text-sm text-text">
          <div className="bg-panel border border-border rounded p-4 flex flex-col gap-1">
            <span className="text-xs text-muted">Apply rate</span>
            <span className="font-mono text-xl text-teal">
              {stats?.total_matches
                ? `${Math.round((stats.total_applied / stats.total_matches) * 100)}%`
                : "—"}
            </span>
            <span className="text-xs text-muted">of matches auto-applied</span>
          </div>
          <div className="bg-panel border border-border rounded p-4 flex flex-col gap-1">
            <span className="text-xs text-muted">Interview rate</span>
            <span className="font-mono text-xl text-amber">
              {stats?.total_applied
                ? `${Math.round(((stats.interviews ?? 0) / stats.total_applied) * 100)}%`
                : "—"}
            </span>
            <span className="text-xs text-muted">of applications → interview</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tab: Matches ───────────────────────────────────────────
function MatchesTab({ matches, onRefresh }: { matches: Match[]; onRefresh: () => void }) {
  const [selected, setSelected] = useState<Match | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "applied">("all");

  const filtered = matches.filter(m =>
    filter === "all" ? true :
    filter === "pending" ? !m.applied :
    m.applied
  );

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center gap-2">
        {(["all", "pending", "applied"] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded border transition-colors capitalize ${
              filter === f
                ? "bg-teal/10 border-teal/40 text-teal"
                : "border-border text-muted hover:text-text"
            }`}
          >
            {f}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted">{filtered.length} results</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {["Role", "Company", "Resume", "Score", "Status", ""].map(h => (
                <th key={h} className="text-left text-xs text-muted font-normal pb-2 pr-4 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((m, i) => (
              <tr
                key={i}
                className="border-b border-border/50 hover:bg-panel/60 cursor-pointer transition-colors group"
                onClick={() => setSelected(m)}
              >
                <td className="py-2.5 pr-4 text-text font-medium max-w-[200px] truncate">{m.job_title}</td>
                <td className="py-2.5 pr-4 text-muted">{m.company}</td>
                <td className="py-2.5 pr-4">
                  <span className="text-xs bg-panel border border-border text-text px-2 py-0.5 rounded">{m.resume_label}</span>
                </td>
                <td className="py-2.5 pr-4"><ScoreBadge score={m.score} /></td>
                <td className="py-2.5 pr-4">
                  {m.applied
                    ? <StatusPill status={m.apply_status ?? "applied"} />
                    : <span className="text-xs text-muted">—</span>}
                </td>
                <td className="py-2.5 text-muted text-xs opacity-0 group-hover:opacity-100 transition-opacity">view →</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="py-12 text-center text-muted text-sm">No matches yet. Run the pipeline to get started.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <MatchDrawer
          match={selected}
          onClose={() => setSelected(null)}
          onApplied={() => { onRefresh(); setSelected(null); }}
        />
      )}
    </div>
  );
}

// ── Tab: Applications ──────────────────────────────────────
function ApplicationsTab({ apps, onRefresh }: { apps: Application[]; onRefresh: () => void }) {
  const [coverApp, setCoverApp] = useState<Application | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const statusOrder = ["applied", "interview", "offer", "rejected", "ghosted", "failed"];

  async function handleStatus(app: Application, status: string) {
    setUpdatingId(app.id);
    try {
      await updateAppStatus(app.id, status);
      onRefresh();
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {["Role", "Company", "Resume", "Score", "Applied", "Status", "Actions"].map(h => (
                <th key={h} className="text-left text-xs text-muted font-normal pb-2 pr-4 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {apps.map((app, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-panel/30 transition-colors group">
                <td className="py-2.5 pr-4 text-text font-medium max-w-[180px] truncate">{app.job_title}</td>
                <td className="py-2.5 pr-4 text-muted">{app.company}</td>
                <td className="py-2.5 pr-4 text-xs text-muted">{app.resume_label}</td>
                <td className="py-2.5 pr-4"><ScoreBadge score={app.match_score} /></td>
                <td className="py-2.5 pr-4 text-xs text-muted whitespace-nowrap">
                  {new Date(app.applied_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </td>
                <td className="py-2.5 pr-4"><StatusPill status={app.status} /></td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => setCoverApp(app)}
                      className="text-xs text-muted hover:text-text transition-colors"
                    >letter</button>
                    <select
                      className="text-xs bg-panel border border-border text-muted rounded px-1 py-0.5 outline-none cursor-pointer hover:border-teal/40 transition-colors"
                      value={app.status}
                      disabled={updatingId === app.id}
                      onChange={e => handleStatus(app, e.target.value)}
                    >
                      {statusOrder.map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </td>
              </tr>
            ))}
            {apps.length === 0 && (
              <tr><td colSpan={7} className="py-12 text-center text-muted text-sm">No applications yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {coverApp && <CoverDrawer app={coverApp} onClose={() => setCoverApp(null)} />}
    </div>
  );
}

// ── Tab: Resumes ───────────────────────────────────────────
function ResumesTab({ resumes, onRefresh }: { resumes: Resume[]; onRefresh: () => void }) {
  const [showUpload, setShowUpload] = useState(false);

  async function handleDelete(id: string) {
    if (!confirm("Remove this resume?")) return;
    await deleteResume(id);
    onRefresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted">{resumes.length} active resume{resumes.length !== 1 ? "s" : ""}</div>
        <button
          onClick={() => setShowUpload(true)}
          className="text-xs bg-teal text-ink font-semibold px-3 py-1.5 rounded hover:bg-teal/90 transition-colors"
        >
          + Upload resume
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {resumes.map(r => (
          <div key={r.id} className="flex items-center gap-4 bg-panel border border-border rounded px-4 py-3">
            <span className="text-lg">📄</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-text">{r.label}</div>
              <div className="text-xs text-muted truncate">{r.filename}</div>
            </div>
            <div className="text-xs text-muted whitespace-nowrap">
              {new Date(r.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            </div>
            <button
              onClick={() => handleDelete(r.id)}
              className="text-xs text-muted hover:text-rose transition-colors ml-2"
            >
              remove
            </button>
          </div>
        ))}
        {resumes.length === 0 && (
          <div className="py-12 text-center text-muted text-sm border border-dashed border-border rounded">
            No resumes yet. Upload one to get started.
          </div>
        )}
      </div>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onDone={() => { setShowUpload(false); onRefresh(); }}
        />
      )}
    </div>
  );
}

// ── Tab: Jobs feed ─────────────────────────────────────────
function JobsTab({ jobs }: { jobs: Job[] }) {
  const [source, setSource] = useState<string>("all");
  const sources = ["all", ...Array.from(new Set(jobs.map(j => j.source)))];
  const filtered = source === "all" ? jobs : jobs.filter(j => j.source === source);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 flex-wrap">
        {sources.map(s => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={`text-xs px-3 py-1.5 rounded border transition-colors capitalize ${
              source === s
                ? "bg-teal/10 border-teal/40 text-teal"
                : "border-border text-muted hover:text-text"
            }`}
          >
            {s}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted">{filtered.length} listings</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {["Role", "Company", "Location", "Source", "Fetched", ""].map(h => (
                <th key={h} className="text-left text-xs text-muted font-normal pb-2 pr-4 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((j, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-panel/40 transition-colors">
                <td className="py-2.5 pr-4 text-text max-w-[200px] truncate">{j.title}</td>
                <td className="py-2.5 pr-4 text-muted">{j.company}</td>
                <td className="py-2.5 pr-4 text-xs text-muted">{j.remote ? "Remote" : j.location || "—"}</td>
                <td className="py-2.5 pr-4"><SourceTag source={j.source} /></td>
                <td className="py-2.5 pr-4 text-xs text-muted whitespace-nowrap">
                  {new Date(j.fetched_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </td>
                <td className="py-2.5">
                  <a
                    href={j.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-teal hover:underline"
                    onClick={e => e.stopPropagation()}
                  >
                    view
                  </a>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="py-12 text-center text-muted text-sm">No jobs fetched yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// ROOT APP
// ══════════════════════════════════════════
type Tab = "dashboard" | "matches" | "applications" | "resumes" | "jobs";

export default function Home() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [stats, setStats] = useState<Stats | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [s, m, a, r, j] = await Promise.allSettled([
      getStats(), getMatches(0), getApplications(), getResumes(), getJobs(),
    ]);
    if (s.status === "fulfilled") setStats(s.value);
    if (m.status === "fulfilled") setMatches(m.value);
    if (a.status === "fulfilled") setApps(a.value);
    if (r.status === "fulfilled") setResumes(r.value);
    if (j.status === "fulfilled") setJobs(j.value);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handlePipeline() {
    setPipelineRunning(true);
    try {
      await triggerPipeline();
      setLastRun(new Date().toLocaleTimeString());
      setTimeout(load, 3000);
    } finally {
      setPipelineRunning(false);
    }
  }

  const pendingMatches = matches.filter(m => !m.applied).length;

  const navItems: { id: Tab; icon: string; label: string; badge?: number }[] = [
    { id: "dashboard",    icon: "◈",  label: "Overview" },
    { id: "matches",      icon: "⟐",  label: "Matches",      badge: pendingMatches },
    { id: "applications", icon: "✉",  label: "Applications", badge: apps.filter(a => a.status === "interview").length },
    { id: "resumes",      icon: "📄", label: "Resumes",      badge: resumes.length },
    { id: "jobs",         icon: "⊞",  label: "Jobs feed" },
  ];

  return (
    <>
      <div className="flex h-screen overflow-hidden bg-ink">

        {/* Sidebar */}
        <aside className="w-52 shrink-0 bg-surface border-r border-border flex flex-col">
          {/* Logo */}
          <div className="px-4 py-5 border-b border-border">
            <div className="flex items-center gap-2">
              <span className="text-teal font-mono font-bold text-lg">JB</span>
              <span className="text-text font-semibold text-sm">JobBot</span>
            </div>
            <div className="text-xs text-muted mt-0.5">AI application engine</div>
          </div>

          {/* Nav */}
          <nav className="flex-1 py-3 flex flex-col gap-0.5">
            {navItems.map(item => (
              <NavItem
                key={item.id}
                icon={item.icon}
                label={item.label}
                active={tab === item.id}
                badge={item.badge}
                onClick={() => setTab(item.id)}
              />
            ))}
          </nav>

          {/* Pipeline trigger */}
          <div className="p-4 border-t border-border flex flex-col gap-2">
            <button
              onClick={handlePipeline}
              disabled={pipelineRunning}
              className="w-full text-xs font-semibold py-2 rounded bg-teal text-ink hover:bg-teal/90 disabled:opacity-50 transition-colors"
            >
              {pipelineRunning ? "Running…" : "▶ Run pipeline"}
            </button>
            {lastRun && <div className="text-xs text-muted text-center">Last run {lastRun}</div>}
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 flex flex-col overflow-hidden">

          {/* Top stats strip */}
          <div className="border-b border-border flex overflow-x-auto shrink-0">
            <StatCard label="Jobs fetched"  value={stats?.total_jobs ?? 0} />
            <StatCard label="Resumes"       value={stats?.total_resumes ?? 0} />
            <StatCard label="Matches ≥70%"  value={stats?.total_matches ?? 0} accent="text-sky" />
            <StatCard label="Applied"       value={stats?.total_applied ?? 0} accent="text-teal" />
            <StatCard label="Interviews"    value={stats?.interviews ?? 0} accent="text-amber" />
            <StatCard label="Offers"        value={stats?.offers ?? 0} accent="text-teal" />
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {tab === "dashboard"    && <DashboardTab stats={stats} />}
            {tab === "matches"      && <MatchesTab matches={matches} onRefresh={load} />}
            {tab === "applications" && <ApplicationsTab apps={apps} onRefresh={load} />}
            {tab === "resumes"      && <ResumesTab resumes={resumes} onRefresh={load} />}
            {tab === "jobs"         && <JobsTab jobs={jobs} />}
          </div>
        </main>
      </div>
    </>
  );
}
