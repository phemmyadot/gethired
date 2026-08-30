import { useState } from "react";
import { type Match, type Resume } from "../../lib/api";
import { ScoreBadge, StatusPill, WorkModeTag } from "../ui";
import { MatchDrawer } from "../MatchDrawer";

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
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
          {filtered.map((m, i) => (
            <div
              key={i}
              onClick={() => setSelected(m)}
              className="bg-surface rounded-xl2 border border-border/60 shadow-card hover:shadow-card-hover transition-shadow p-5 flex flex-col gap-4 cursor-pointer"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-display text-lg font-semibold text-ink leading-snug truncate">{m.job_title}</div>
                  <div className="text-sm text-muted mt-0.5">
                    {m.company}{m.location ? ` · ${m.location}` : ""}
                  </div>
                </div>
                <ScoreBadge score={m.score} />
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <WorkModeTag mode={m.work_mode} />
                <span className="text-xs bg-panel text-ink/70 px-2.5 py-1 rounded-full">{m.resume_label}</span>
                <span className="text-xs text-muted">
                  {new Date(m.posted_at ?? m.reviewed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </span>
              </div>

              <div className="flex items-center justify-between gap-2 mt-auto pt-3 border-t border-border/60">
                {m.applied && m.application_id ? (
                  <button
                    onClick={e => { e.stopPropagation(); onViewApplication(m.application_id!); }}
                    className="hover:opacity-80 transition-opacity"
                  >
                    <StatusPill status={m.apply_status ?? "applied"} />
                  </button>
                ) : (
                  <span className="text-sm text-muted">Not applied</span>
                )}
                {m.apply_url && (
                  <a
                    href={m.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-semibold px-4 py-2 rounded-full bg-accent-soft text-accent hover:bg-accent hover:text-white transition-colors"
                    onClick={e => e.stopPropagation()}
                  >
                    View listing
                  </a>
                )}
              </div>
            </div>
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
