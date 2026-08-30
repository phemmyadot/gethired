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
    <aside className="w-52 shrink-0 bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <img src="/icon.svg" alt="" width={22} height={22} className="rounded" />
          <span className="text-text font-semibold text-sm">JobBot</span>
        </div>
        <div className="text-xs text-muted mt-0.5">AI application engine</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 flex flex-col gap-0.5">
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
      <div className="p-4 border-t border-border flex flex-col gap-2">
        <button
          onClick={onRunPipeline}
          disabled={pipelineRunning || !!inProgress}
          className="w-full text-xs font-semibold py-2 rounded bg-teal text-ink hover:bg-teal/90 disabled:opacity-50 transition-colors"
        >
          {pipelineRunning || inProgress ? "Running…" : "▶ Run pipeline"}
        </button>

        {inProgress && pipelineStatus && (
          <div className="text-xs text-muted flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5 text-teal">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-teal animate-pulse" />
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
          <div className="text-xs text-rose">{pipelineStatus.error ?? "Pipeline failed"}</div>
        )}

        {lastRun && <div className="text-xs text-muted text-center">Last run {lastRun}</div>}
      </div>
    </aside>
  );
}
