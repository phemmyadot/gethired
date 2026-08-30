import { NavItem } from "./ui";

export type Tab = "dashboard" | "matches" | "applications" | "resumes" | "jobs";

type NavItemDef = { id: Tab; icon: string; label: string; badge?: number };

export function Sidebar({ tab, onTabChange, navItems, pipelineRunning, onRunPipeline, lastRun }: {
  tab: Tab;
  onTabChange: (t: Tab) => void;
  navItems: NavItemDef[];
  pipelineRunning: boolean;
  onRunPipeline: () => void;
  lastRun: string | null;
}) {
  return (
    <aside className="w-52 shrink-0 bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-teal font-mono font-bold text-lg">JB</span>
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
          disabled={pipelineRunning}
          className="w-full text-xs font-semibold py-2 rounded bg-teal text-ink hover:bg-teal/90 disabled:opacity-50 transition-colors"
        >
          {pipelineRunning ? "Running…" : "▶ Run pipeline"}
        </button>
        {lastRun && <div className="text-xs text-muted text-center">Last run {lastRun}</div>}
      </div>
    </aside>
  );
}
