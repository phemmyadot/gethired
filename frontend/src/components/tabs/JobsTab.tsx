import { useState, useEffect, useCallback } from "react";
import { getJobs, type Job, type PipelineStatus } from "../../lib/api";
import { JobCard, type JobCardData } from "../JobCard";

const PAGE_SIZE = 48;

function toCardData(j: Job): JobCardData {
  return {
    id: j.id,
    title: j.title,
    company: j.company,
    source: j.source,
    location: j.location,
    workMode: j.work_mode,
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

export function JobsTab({ onViewApplication, onMatchAll, matching, matchProgress, reloadKey }: {
  onViewApplication: (applicationId: string) => void;
  onMatchAll: () => void;
  matching: boolean;
  matchProgress: PipelineStatus;
  reloadKey: number;
}) {
  const [source, setSource] = useState<string>("all");
  const [sort, setSort] = useState<"fetched" | "score">("fetched");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

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

  const sources = ["all", "adzuna", "remotive", "remoteok", "jobicy", "arbeitnow", "greenhouse", "lever"];
  const hasMore = jobs.length < total;

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
          {matching
            ? `Matching… ${matchProgress?.matches_found ?? 0}/${matchProgress?.jobs_found ?? 0}`
            : "Match / rematch all"}
        </button>

        <div className="ml-auto flex items-center gap-3">
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
              <JobCard key={i} job={toCardData(j)} onViewApplication={onViewApplication} />
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
    </div>
  );
}
