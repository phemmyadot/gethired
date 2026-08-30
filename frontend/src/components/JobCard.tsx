import { type WorkMode } from "../lib/api";
import { SourceTag, WorkModeTag, ScoreBadge, StatusPill } from "./ui";

export type JobCardData = {
  title: string;
  company: string;
  source: string;
  location: string | null;
  workMode: WorkMode;
  applyUrl: string;
  postedAt: string;              // ISO date to display — caller resolves the best fallback
  score?: number;                 // present for matches only
  resumeLabel?: string;           // present for matches only
  applied: boolean;
  applyStatus: string | null;
  applicationId: string | null;
};

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

export function JobCard({ job, onClick, onViewApplication }: {
  job: JobCardData;
  onClick?: () => void;
  onViewApplication: (applicationId: string) => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`bg-surface rounded-xl2 border border-border/60 shadow-card hover:shadow-card-hover transition-shadow p-5 flex flex-col gap-4 ${onClick ? "cursor-pointer" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center font-display font-semibold text-lg shrink-0 ${avatarStyle(job.company)}`}>
            {job.company.charAt(0).toUpperCase() || "?"}
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-ink truncate">{job.company}</div>
            <div className="text-xs text-muted truncate">{job.location || "Location unknown"}</div>
          </div>
        </div>
        {job.score != null ? <ScoreBadge score={job.score} /> : <span className="text-xs text-muted">—</span>}
      </div>

      <div>
        <div className="font-display text-lg font-semibold text-ink leading-snug">{job.title}</div>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <WorkModeTag mode={job.workMode} />
          <SourceTag source={job.source} />
          <span className="text-xs bg-panel text-ink/70 px-2.5 py-1 rounded-full">
            {job.resumeLabel ?? "Not matched"}
          </span>
          <span className="text-xs text-muted">{timeAgo(job.postedAt)}</span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 mt-auto pt-3 border-t border-border/60">
        {job.applied && job.applicationId ? (
          <button
            onClick={e => { e.stopPropagation(); onViewApplication(job.applicationId!); }}
            className="hover:opacity-80 transition-opacity"
          >
            <StatusPill status={job.applyStatus ?? "applied"} />
          </button>
        ) : (
          <span className="text-sm text-muted">Not applied</span>
        )}
        <a
          href={job.applyUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-semibold px-4 py-2 rounded-full bg-accent-soft text-accent hover:bg-accent hover:text-white transition-colors"
          onClick={e => e.stopPropagation()}
        >
          View listing
        </a>
      </div>
    </div>
  );
}
