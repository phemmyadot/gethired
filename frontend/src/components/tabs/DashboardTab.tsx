import { type Stats } from "../../lib/api";

export function DashboardTab({ stats }: { stats: Stats | null }) {
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
