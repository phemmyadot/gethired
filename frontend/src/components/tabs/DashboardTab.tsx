import { type Stats } from "../../lib/api";

export function DashboardTab({ stats }: { stats: Stats | null }) {
  const threshold = Math.round((stats?.score_threshold ?? 0.7) * 100);
  const funnelSteps = [
    { label: "Jobs fetched",     value: stats?.total_jobs ?? 0,     color: "bg-sky",   text: "text-sky",   soft: "bg-sky-soft" },
    { label: `Matches ≥${threshold}%`, value: stats?.total_matches ?? 0, color: "bg-accent", text: "text-accent", soft: "bg-accent-soft" },
    { label: "Applied",          value: stats?.total_applied ?? 0,  color: "bg-teal",  text: "text-teal",  soft: "bg-teal-soft" },
    { label: "Interviews",       value: stats?.interviews ?? 0,     color: "bg-amber", text: "text-amber", soft: "bg-amber-soft" },
    { label: "Offers",           value: stats?.offers ?? 0,         color: "bg-teal",  text: "text-teal",  soft: "bg-teal-soft" },
  ];

  const max = Math.max(...funnelSteps.map(s => s.value), 1);

  return (
    <div className="flex flex-col gap-8">
      <div className="bg-surface rounded-xl2 border border-border/60 shadow-card p-6">
        <h2 className="font-display text-lg font-semibold text-ink mb-6">Pipeline funnel</h2>
        <div className="flex flex-col gap-3">
          {funnelSteps.map((step, i) => {
            const width = Math.max((step.value / max) * 100, 3);
            return (
              <div key={i} className="flex items-center gap-4">
                <div className="w-32 text-sm text-muted text-right shrink-0">{step.label}</div>
                <div className={`flex-1 ${step.soft} rounded-full h-9 overflow-hidden`}>
                  <div
                    className={`h-full ${step.color} rounded-full transition-all duration-700 flex items-center pl-4`}
                    style={{ width: `${width}%` }}
                  >
                    <span className="font-mono text-sm font-semibold text-white">{step.value}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="font-display text-lg font-semibold text-ink mb-4">At a glance</h2>
        <div className="grid grid-cols-3 gap-5">
          <div className="bg-surface rounded-xl2 border border-border/60 shadow-card p-6 flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted uppercase tracking-wide">Apply rate</span>
            <span className="font-display text-3xl font-semibold text-teal">
              {stats?.total_matches
                ? `${Math.round(((stats.applied_with_match ?? 0) / stats.total_matches) * 100)}%`
                : "—"}
            </span>
            <span className="text-sm text-muted">of matches applied to</span>
          </div>
          <div className="bg-surface rounded-xl2 border border-border/60 shadow-card p-6 flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted uppercase tracking-wide">Applied were matched</span>
            <span className="font-display text-3xl font-semibold text-sky">
              {stats?.total_applied_all
                ? `${Math.round(((stats.applied_with_match ?? 0) / stats.total_applied_all) * 100)}%`
                : "—"}
            </span>
            <span className="text-sm text-muted">of applied jobs cleared the match threshold</span>
          </div>
          <div className="bg-surface rounded-xl2 border border-border/60 shadow-card p-6 flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted uppercase tracking-wide">Interview rate</span>
            <span className="font-display text-3xl font-semibold text-amber">
              {stats?.total_applied
                ? `${Math.round(((stats.interviews ?? 0) / stats.total_applied) * 100)}%`
                : "—"}
            </span>
            <span className="text-sm text-muted">of applications → interview</span>
          </div>
        </div>
      </div>
    </div>
  );
}
