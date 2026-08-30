import { NavItem } from "./ui";
import { type PipelineStatus } from "../lib/api";

export type Tab = "dashboard" | "matches" | "applications" | "resumes" | "jobs";

type NavItemDef = { id: Tab; icon: string; label: string; badge?: number };

const STAGE_LABELS: Record<string, string> = {
  running:   "Starting…",
  ingesting: "Fetching jobs…",
  matching:  "Scoring matches…",
  applying:  "Applying…",
  done:      "Done",
  failed:    "Failed",
};

export function Sidebar({ tab, onTabChange, navItems, pipelineRunning, onRunPipeline, lastRun, pipelineStatus }: {
  tab: Tab;
  onTabChange: (t: Tab) => void;
  navItems: NavItemDef[];
  pipelineRunning: boolean;
  onRunPipeline: () => void;
  lastRun: string | null;
  pipelineStatus: PipelineStatus;
}) {
  const inProgress = pipelineStatus && ["running", "ingesting", "matching", "applying"].includes(pipelineStatus.status);
  return (
    <aside className="w-60 shrink-0 bg-paper border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-5 py-6">
        <div className="flex items-center gap-2.5">
          <img src="/icon.svg" alt="" width={30} height={30} className="rounded-lg" />
          <span className="font-display text-xl font-semibold text-ink">JobBot</span>
        </div>
        <div className="text-xs text-muted mt-1 pl-[2px]">AI application engine</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 flex flex-col gap-1">
        {navItems.map(item => (
          <NavItem
            key={item.id}
            icon={item.icon}
            label={item.label}
            active={tab === item.id}
            badge={item.badge}
            onClick={() => onTabChange(item.id)}
          />
        ))}
      </nav>

      {/* Pipeline trigger */}
      <div className="p-4 flex flex-col gap-3">
        <div className="h-px bg-border" />
        <button
          onClick={onRunPipeline}
          disabled={pipelineRunning || !!inProgress}
          className="w-full text-sm font-semibold py-2.5 rounded-xl bg-ink text-paper hover:bg-ink/85 disabled:opacity-50 transition-colors shadow-card"
        >
          {pipelineRunning || inProgress ? "Running…" : "Run pipeline"}
        </button>

        {inProgress && pipelineStatus && (
          <div className="text-xs text-muted flex flex-col gap-1 bg-panel rounded-xl px-3 py-2.5">
            <div className="flex items-center gap-1.5 text-accent font-medium">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              {STAGE_LABELS[pipelineStatus.status] ?? pipelineStatus.status}
            </div>
            {pipelineStatus.jobs_found > 0 && (
              <div>{pipelineStatus.jobs_new} new / {pipelineStatus.jobs_found} found</div>
            )}
            {pipelineStatus.matches_found > 0 && (
              <div>{pipelineStatus.matches_found} matches</div>
            )}
          </div>
        )}

        {!inProgress && pipelineStatus?.status === "failed" && (
          <div className="text-xs text-rose bg-rose-soft rounded-xl px-3 py-2.5">{pipelineStatus.error ?? "Pipeline failed"}</div>
        )}

        {lastRun && <div className="text-xs text-muted text-center">Last run {lastRun}</div>}
      </div>
    </aside>
  );
}
