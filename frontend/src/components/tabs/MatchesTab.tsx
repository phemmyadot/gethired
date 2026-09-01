import { useState } from "react";
import { type Match, type Resume } from "../../lib/api";
import { JobCard, type JobCardData } from "../JobCard";
import { MatchDrawer } from "../MatchDrawer";

function toCardData(m: Match): JobCardData {
  return {
    id: m.job_id,
    title: m.job_title,
    company: m.company,
    source: m.source,
    location: m.location,
    workMode: m.work_mode,
    keySkills: m.key_skills,
    applyUrl: m.apply_url,
    postedAt: m.posted_at,
    fetchedAt: m.fetched_at ?? m.reviewed_at,
    score: m.score,
    resumeLabel: m.resume_label,
    applied: m.applied,
    applyStatus: m.apply_status,
    applicationId: m.application_id,
  };
}

export function MatchesTab({ matches, resumes, onRefresh, onViewApplication }: {
  matches: Match[]; resumes: Resume[]; onRefresh: () => void; onViewApplication: (applicationId: string) => void;
}) {
  const [selected, setSelected] = useState<Match | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "applied">("all");

  const filtered = matches.filter(m =>
    filter === "all" ? true :
    filter === "pending" ? !m.applied :
    m.applied
  );

  const profiledResumes = resumes.filter(r => r.search_keywords || r.required_keywords.length > 0);

  return (
    <div className="flex flex-col gap-6">
      {profiledResumes.length > 0 && (
        <div className="bg-accent-soft rounded-xl2 p-5 flex flex-col gap-3">
          <div className="text-xs font-medium text-accent uppercase tracking-wide">
            Searching for, based on your resume{profiledResumes.length !== 1 ? "s" : ""}
          </div>
          <div className="flex flex-col gap-2.5">
            {profiledResumes.map(r => (
              <div key={r.id} className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-medium bg-white text-accent px-2.5 py-1 rounded-full whitespace-nowrap">
                  {r.label}
                </span>
                {r.search_keywords && (
                  <span className="font-display text-base text-ink">"{r.search_keywords}"</span>
                )}
                {r.required_keywords.map((k, i) => (
                  <span key={i} className="text-xs bg-white/70 text-ink/70 px-2.5 py-1 rounded-full">
                    {k}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        {(["all", "pending", "applied"] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs font-medium px-3.5 py-1.5 rounded-full transition-colors capitalize ${
              filter === f
                ? "bg-ink text-paper"
                : "bg-panel text-muted hover:text-ink"
            }`}
          >
            {f}
          </button>
        ))}
        <span className="ml-auto text-sm text-muted">{filtered.length} results</span>
      </div>

      {filtered.length === 0 ? (
        <div className="py-20 text-center text-muted text-sm bg-surface rounded-xl2 border border-dashed border-border">
          No matches yet. Run the pipeline to get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-5">
          {filtered.map((m, i) => (
            <JobCard
              key={i}
              job={toCardData(m)}
              onClick={() => setSelected(m)}
              onViewApplication={onViewApplication}
            />
          ))}
        </div>
      )}

      {selected && (
        <MatchDrawer
          match={selected}
          onClose={() => setSelected(null)}
          onApplied={() => { onRefresh(); setSelected(null); }}
          onViewApplication={onViewApplication}
        />
      )}
    </div>
  );
}
