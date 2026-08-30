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
    <div className="flex flex-col gap-4 h-full">
      {profiledResumes.length > 0 && (
        <div className="bg-panel border border-border rounded p-4 flex flex-col gap-2">
          <div className="text-xs text-muted">Searching for, based on your resume{profiledResumes.length !== 1 ? "s" : ""}</div>
          <div className="flex flex-col gap-2">
            {profiledResumes.map(r => (
              <div key={r.id} className="flex items-center gap-2 flex-wrap">
                <span className="text-xs bg-teal/10 border border-teal/30 text-teal px-2 py-0.5 rounded whitespace-nowrap">
                  {r.label}
                </span>
                {r.search_keywords && (
                  <span className="text-sm text-text font-medium">"{r.search_keywords}"</span>
                )}
                {r.required_keywords.map((k, i) => (
                  <span key={i} className="text-xs bg-panel border border-border text-muted px-2 py-0.5 rounded">
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
              {["Role", "Company", "Work mode", "Listed", "Resume", "Score", "Status", "", ""].map(h => (
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
                <td className="py-2.5 pr-4"><WorkModeTag mode={m.work_mode} /></td>
                <td className="py-2.5 pr-4 text-xs text-muted whitespace-nowrap">
                  {m.posted_at ? new Date(m.posted_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "—"}
                </td>
                <td className="py-2.5 pr-4">
                  <span className="text-xs bg-panel border border-border text-text px-2 py-0.5 rounded">{m.resume_label}</span>
                </td>
                <td className="py-2.5 pr-4"><ScoreBadge score={m.score} /></td>
                <td className="py-2.5 pr-4">
                  {m.applied && m.application_id ? (
                    <button
                      onClick={e => { e.stopPropagation(); onViewApplication(m.application_id!); }}
                      className="hover:opacity-80 transition-opacity"
                    >
                      <StatusPill status={m.apply_status ?? "applied"} />
                    </button>
                  ) : (
                    <span className="text-xs text-muted">—</span>
                  )}
                </td>
                <td className="py-2.5 pr-4">
                  {m.apply_url && (
                    <a
                      href={m.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-sky hover:underline"
                      onClick={e => e.stopPropagation()}
                    >
                      view listing
                    </a>
                  )}
                </td>
                <td className="py-2.5 text-muted text-xs opacity-0 group-hover:opacity-100 transition-opacity">view →</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="py-12 text-center text-muted text-sm">No matches yet. Run the pipeline to get started.</td></tr>
            )}
          </tbody>
        </table>
      </div>

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
