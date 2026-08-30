import { useState } from "react";
import { type Job } from "../../lib/api";
import { SourceTag, WorkModeTag } from "../ui";

const AVATAR_COLORS = [
  "bg-accent-soft text-accent", "bg-teal-soft text-teal",
  "bg-amber-soft text-amber", "bg-sky-soft text-sky", "bg-rose-soft text-rose",
];

function avatarStyle(seed: string) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function timeAgo(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${Math.max(mins, 0)}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
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
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
          {filtered.map((j, i) => (
            <div
              key={i}
              className="bg-surface rounded-xl2 border border-border/60 shadow-card hover:shadow-card-hover transition-shadow p-5 flex flex-col gap-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center font-display font-semibold text-lg shrink-0 ${avatarStyle(j.company)}`}>
                    {j.company.charAt(0).toUpperCase() || "?"}
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-ink truncate">{j.company}</div>
                    <div className="text-xs text-muted">{j.location || "Location unknown"}</div>
                  </div>
                </div>
                <SourceTag source={j.source} />
              </div>

              <div>
                <div className="font-display text-lg font-semibold text-ink leading-snug">{j.title}</div>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <WorkModeTag mode={j.work_mode} />
                  <span className="text-xs text-muted">{timeAgo(j.posted_at ?? j.fetched_at)}</span>
                </div>
              </div>

              <div className="flex items-center justify-between gap-2 mt-auto pt-3 border-t border-border/60">
                {j.applied && j.application_id ? (
                  <button
                    onClick={() => onViewApplication(j.application_id!)}
                    className="text-sm font-medium text-teal hover:underline"
                  >
                    View application
                  </button>
                ) : (
                  <span className="text-sm text-muted">Not applied</span>
                )}
                <a
                  href={j.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold px-4 py-2 rounded-full bg-accent-soft text-accent hover:bg-accent hover:text-white transition-colors"
                >
                  View listing
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
