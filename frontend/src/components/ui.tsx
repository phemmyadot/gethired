// ── Score badge ────────────────────────────────────────────
export function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 85 ? "text-teal border-teal/40 bg-teal/10" :
    pct >= 70 ? "text-sky border-sky/40 bg-sky/10" :
    pct >= 50 ? "text-amber border-amber/40 bg-amber/10" :
               "text-muted border-border bg-panel";
  return (
    <span className={`font-mono text-xs px-2 py-0.5 rounded border ${color}`}>
      {pct}%
    </span>
  );
}

// ── Status pill ────────────────────────────────────────────
export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    applied:   "text-teal  bg-teal/10  border-teal/30",
    interview: "text-amber bg-amber/10 border-amber/30",
    offer:     "text-teal  bg-teal/20  border-teal/50",
    rejected:  "text-rose  bg-rose/10  border-rose/30",
    failed:    "text-rose  bg-rose/10  border-rose/30",
    ghosted:   "text-muted bg-panel    border-border",
    skipped:   "text-muted bg-panel    border-border",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded border capitalize ${map[status] ?? "text-muted border-border"}`}>
      {status}
    </span>
  );
}

// ── Source tag ─────────────────────────────────────────────
export function SourceTag({ source }: { source: string }) {
  const colors: Record<string, string> = {
    adzuna:     "text-sky   border-sky/30",
    remotive:   "text-teal  border-teal/30",
    greenhouse: "text-amber border-amber/30",
    lever:      "text-rose  border-rose/30",
  };
  return (
    <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${colors[source] ?? "text-muted border-border"}`}>
      {source}
    </span>
  );
}

// ── Stat card ──────────────────────────────────────────────
export function StatCard({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="border border-border bg-surface px-5 py-4 flex flex-col gap-1 min-w-[110px]">
      <span className={`font-mono text-2xl font-bold ${accent ?? "text-text"}`}>{value}</span>
      <span className="text-xs text-muted">{label}</span>
    </div>
  );
}

// ── Sidebar nav item ───────────────────────────────────────
export function NavItem({ icon, label, active, onClick, badge }: {
  icon: string; label: string; active: boolean; onClick: () => void; badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors relative
        ${active
          ? "bg-teal/10 text-teal border-r-2 border-teal"
          : "text-muted hover:text-text hover:bg-panel/60"}`}
    >
      <span className="text-base">{icon}</span>
      <span className="flex-1">{label}</span>
      {badge != null && badge > 0 && (
        <span className="text-xs font-mono bg-teal/20 text-teal px-1.5 py-0.5 rounded">{badge}</span>
      )}
    </button>
  );
}
