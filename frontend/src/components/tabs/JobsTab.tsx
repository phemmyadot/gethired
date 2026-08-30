import { useState } from "react";
import { type Job } from "../../lib/api";
import { JobCard, type JobCardData } from "../JobCard";

function toCardData(j: Job): JobCardData {
  return {
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

export function JobsTab({ jobs, onViewApplication }: {
  jobs: Job[]; onViewApplication: (applicationId: string) => void;
}) {
  const [source, setSource] = useState<string>("all");
  const sources = ["all", ...Array.from(new Set(jobs.map(j => j.source)))];
  const filtered = source === "all" ? jobs : jobs.filter(j => j.source === source);

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
        <span className="ml-auto text-sm text-muted">{filtered.length} listings</span>
      </div>

      {filtered.length === 0 ? (
        <div className="py-20 text-center text-muted text-sm bg-surface rounded-xl2 border border-dashed border-border">
          No jobs fetched yet. Run the pipeline to get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-5">
          {filtered.map((j, i) => (
            <JobCard key={i} job={toCardData(j)} onViewApplication={onViewApplication} />
          ))}
        </div>
      )}
    </div>
  );
}
