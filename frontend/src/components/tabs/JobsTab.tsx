import { useState, useEffect, useCallback } from "react";
import { getJobs, type Job, type Match, type PipelineStatus } from "../../lib/api";
import { JobCard, type JobCardData } from "../JobCard";
import { MatchDrawer } from "../MatchDrawer";

const PAGE_SIZE = 48;

function toCardData(j: Job): JobCardData {
  return {
    id: j.id,
    title: j.title,
    company: j.company,
    source: j.source,
    location: j.location,
    workMode: j.work_mode,
    keySkills: j.key_skills,
    applyUrl: j.apply_url,
    postedAt: j.posted_at,
    fetchedAt: j.fetched_at,
    score: j.score ?? undefined,
    resumeLabel: j.resume_label ?? undefined,
    applied: j.applied,
    applyStatus: j.applied ? "applied" : null,
    applicationId: j.application_id,
  };
}

function toMatch(j: Job): Match | null {
  if (j.score == null || !j.resume_id) return null;
  return {
    job_id: j.id,
    resume_id: j.resume_id,
    resume_label: j.resume_label ?? "",
    job_title: j.title,
    company: j.company,
    apply_url: j.apply_url,
    source: j.source,
    location: j.location,
    remote: j.remote,
    work_mode: j.work_mode,
    key_skills: j.key_skills,
    posted_at: j.posted_at,
    fetched_at: j.fetched_at,
    score: j.score,
    reasoning: j.reasoning ?? "",
    missing_skills: j.missing_skills ?? [],
    selling_points: j.selling_points ?? [],
    applied: j.applied,
    apply_status: j.apply_status,
    application_id: j.application_id,
    reviewed_at: j.fetched_at,
  };
}

export function JobsTab({ onViewApplication, onMatchAll, onMatchSelected, onStopMatchAll, matching, canStop, matchProgress, reloadKey, totalScoredJobs }: {
  onViewApplication: (applicationId: string) => void;
  onMatchAll: () => void;
  onMatchSelected: (jobIds: string[]) => void;
  onStopMatchAll: () => void;
  matching: boolean;
  canStop: boolean;
  matchProgress: PipelineStatus;
  reloadKey: number;
  totalScoredJobs: number;
}) {
  const [source, setSource] = useState<string>("all");
  const [sort, setSort] = useState<"fetched" | "score">("fetched");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectedMatch, setSelectedMatch] = useState<Match | null>(null);

  const loadPage = useCallback(async (sourceFilter: string, sortBy: "fetched" | "score", offset: number) => {
    return getJobs({
      source: sourceFilter === "all" ? undefined : sourceFilter,
      limit: PAGE_SIZE,
      offset,
      sort: sortBy,
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    loadPage(source, sort, 0)
      .then(page => { setJobs(page.items); setTotal(page.total); })
      .finally(() => setLoading(false));
  }, [source, sort, loadPage, reloadKey]);

  useEffect(() => { setSelected(new Set()); }, [source, sort, reloadKey]);

  async function handleLoadMore() {
    setLoadingMore(true);
    try {
      const page = await loadPage(source, sort, jobs.length);
      setJobs(prev => [...prev, ...page.items]);
      setTotal(page.total);
    } finally {
      setLoadingMore(false);
    }
  }

  function toggleSelect(jobId: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId); else next.add(jobId);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected(prev => prev.size === jobs.length ? new Set() : new Set(jobs.map(j => j.id)));
  }

  function handleCardClick(j: Job) {
    const match = toMatch(j);
    if (match) setSelectedMatch(match);
  }

  const sources = ["all", "adzuna", "remotive", "remoteok", "jobicy", "arbeitnow", "greenhouse", "lever"];
  const hasMore = jobs.length < total;
  const allSelected = jobs.length > 0 && selected.size === jobs.length;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2 flex-wrap">
        {sources.map(s => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={`text-xs font-medium px-3.5 py-1.5 rounded-full transition-colors capitalize ${
              source === s
                ? "bg-ink text-paper"
                : "bg-panel text-muted hover:text-ink"
            }`}
          >
            {s}
          </button>
        ))}

        <button
          onClick={onMatchAll}
          disabled={matching}
          className="text-xs font-semibold px-3.5 py-1.5 rounded-full bg-accent text-white hover:bg-accent/90 disabled:opacity-50 transition-colors whitespace-nowrap"
        >
          {matching ? "Matching…" : "Match unmatched"}
        </button>

        {selected.size > 0 && (
          <button
            onClick={() => onMatchSelected(Array.from(selected))}
            disabled={matching}
            className="text-xs font-semibold px-3.5 py-1.5 rounded-full bg-ink text-paper hover:bg-ink/85 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            Match {selected.size} selected
          </button>
        )}

        <span className="text-xs text-muted whitespace-nowrap">
          {totalScoredJobs} matched total
        </span>

        <div className="ml-auto flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleSelectAll}
              className="w-4 h-4 rounded border-border accent-accent cursor-pointer"
            />
            Select all
          </label>
          <div className="flex items-center gap-1 bg-panel rounded-full p-1">
            {(["fetched", "score"] as const).map(s => (
              <button
                key={s}
                onClick={() => setSort(s)}
                className={`text-xs font-medium px-3 py-1 rounded-full transition-colors capitalize ${
                  sort === s ? "bg-ink text-paper" : "text-muted hover:text-ink"
                }`}
              >
                {s === "score" ? "Match %" : "Date fetched"}
              </button>
            ))}
          </div>
          <span className="text-sm text-muted whitespace-nowrap">
            {jobs.length} of {total}
          </span>
        </div>
      </div>

      {matching && (
        <div className="bg-accent-soft rounded-xl2 px-5 py-4 flex items-center gap-4">
          <span className="inline-block w-2 h-2 rounded-full bg-accent animate-pulse shrink-0" />
          <div className="flex-1">
            <div className="flex items-center justify-between text-sm text-ink mb-1.5">
              <span>
                {matchProgress?.status === "stopping" ? "Stopping…" : "Matching jobs against your resume…"}
              </span>
              <span className="font-mono text-accent font-semibold">
                {matchProgress?.matches_found ?? 0} / {matchProgress?.jobs_found ?? 0}
              </span>
            </div>
            <div className="h-1.5 bg-white/60 rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-500"
                style={{
                  width: `${
                    matchProgress?.jobs_found
                      ? Math.min(100, ((matchProgress.matches_found ?? 0) / matchProgress.jobs_found) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
          </div>
          {canStop && (
            <button
              onClick={onStopMatchAll}
              disabled={matchProgress?.status === "stopping"}
              className="text-xs font-semibold px-3.5 py-1.5 rounded-full bg-rose text-white hover:bg-rose/90 disabled:opacity-50 transition-colors whitespace-nowrap shrink-0"
            >
              {matchProgress?.status === "stopping" ? "Stopping…" : "Stop"}
            </button>
          )}
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-muted text-sm">Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="py-20 text-center text-muted text-sm bg-surface rounded-xl2 border border-dashed border-border">
          No jobs fetched yet. Run the pipeline to get started.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-5">
            {jobs.map((j, i) => (
              <JobCard
                key={i}
                job={toCardData(j)}
                onClick={j.score != null ? () => handleCardClick(j) : undefined}
                onViewApplication={onViewApplication}
                selectable
                selected={selected.has(j.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-2">
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="text-sm font-semibold px-6 py-2.5 rounded-full bg-panel text-ink hover:bg-border/60 disabled:opacity-50 transition-colors"
              >
                {loadingMore ? "Loading…" : `Load more (${total - jobs.length} remaining)`}
              </button>
            </div>
          )}
        </>
      )}

      {selectedMatch && (
        <MatchDrawer
          match={selectedMatch}
          onClose={() => setSelectedMatch(null)}
          onApplied={() => setSelectedMatch(null)}
          onViewApplication={onViewApplication}
        />
      )}
    </div>
  );
}
