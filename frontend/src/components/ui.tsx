// ── Score badge ────────────────────────────────────────────
export function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const style =
    pct >= 85 ? "text-teal bg-teal-soft" :
    pct >= 70 ? "text-sky bg-sky-soft" :
    pct >= 50 ? "text-amber bg-amber-soft" :
               "text-muted bg-panel";
  return (
    <span className={`font-mono text-xs font-semibold px-2 py-1 rounded-full ${style}`}>
      {pct}%
    </span>
  );
}

// ── Status pill ────────────────────────────────────────────
export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    applied:   "text-teal  bg-teal-soft",
    interview: "text-amber bg-amber-soft",
    offer:     "text-teal  bg-teal-soft",
    rejected:  "text-rose  bg-rose-soft",
    failed:    "text-rose  bg-rose-soft",
    ghosted:   "text-muted bg-panel",
    skipped:   "text-muted bg-panel",
  };
  return (
    <span className={`text-xs font-medium px-2.5 py-1 rounded-full capitalize ${map[status] ?? "text-muted bg-panel"}`}>
      {status}
    </span>
  );
}

// ── Source tag ─────────────────────────────────────────────
export function SourceTag({ source }: { source: string }) {
  const colors: Record<string, string> = {
    adzuna:     "text-sky   bg-sky-soft",
    remotive:   "text-teal  bg-teal-soft",
    remoteok:   "text-teal  bg-teal-soft",
    jobicy:     "text-sky   bg-sky-soft",
    arbeitnow:  "text-amber bg-amber-soft",
    greenhouse: "text-amber bg-amber-soft",
    lever:      "text-rose  bg-rose-soft",
  };
  return (
    <span className={`text-xs font-mono font-medium px-2 py-1 rounded-full ${colors[source] ?? "text-muted bg-panel"}`}>
      {source}
    </span>
  );
}

// ── Work mode tag ──────────────────────────────────────────
export function WorkModeTag({ mode }: { mode: "remote" | "hybrid" | "onsite" | null }) {
  if (!mode) return <span className="text-xs text-muted">—</span>;
  const colors: Record<string, string> = {
    remote: "text-teal  bg-teal-soft",
    hybrid: "text-amber bg-amber-soft",
    onsite: "text-muted bg-panel",
  };
  return (
    <span className={`text-xs font-medium px-2 py-1 rounded-full capitalize ${colors[mode] ?? "text-muted bg-panel"}`}>
      {mode}
    </span>
  );
}

// ── Stat card ──────────────────────────────────────────────
export function StatCard({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="bg-surface rounded-xl2 shadow-card px-6 py-5 flex flex-col gap-1 min-w-[130px] border border-border/60">
      <span className={`font-display text-3xl font-semibold ${accent ?? "text-ink"}`}>{value}</span>
      <span className="text-xs text-muted uppercase tracking-wide">{label}</span>
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
      className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left rounded-xl transition-all relative
        ${active
          ? "bg-accent text-white shadow-card"
          : "text-ink/70 hover:text-ink hover:bg-panel"}`}
    >
      <span className="text-base">{icon}</span>
      <span className="flex-1 font-medium">{label}</span>
      {badge != null && badge > 0 && (
        <span className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded-full ${
          active ? "bg-white/20 text-white" : "bg-accent-soft text-accent"
        }`}>{badge}</span>
      )}
    </button>
  );
}
