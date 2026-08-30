import { useState, useEffect, useRef } from "react";
import { updateAppStatus, type Application } from "../../lib/api";
import { ScoreBadge, StatusPill } from "../ui";
import { CoverDrawer } from "../CoverDrawer";

export function ApplicationsTab({ apps, onRefresh, focusedAppId, onFocusHandled }: {
  apps: Application[]; onRefresh: () => void;
  focusedAppId?: string | null; onFocusHandled?: () => void;
}) {
  const [coverApp, setCoverApp] = useState<Application | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});

  const statusOrder = ["applied", "interview", "offer", "rejected", "ghosted", "failed"];

  useEffect(() => {
    if (!focusedAppId) return;
    rowRefs.current[focusedAppId]?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = setTimeout(() => onFocusHandled?.(), 2000);
    return () => clearTimeout(timer);
  }, [focusedAppId, onFocusHandled]);

  async function handleStatus(app: Application, status: string) {
    setUpdatingId(app.id);
    try {
      await updateAppStatus(app.id, status);
      onRefresh();
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-surface rounded-xl2 border border-border/60 shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border bg-panel/60">
                {["Role", "Company", "Resume", "Score", "Applied", "Status", "Actions"].map(h => (
                  <th key={h} className="text-left text-xs font-medium text-muted uppercase tracking-wide py-3 px-5 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {apps.map((app, i) => (
                <tr
                  key={i}
                  ref={el => { rowRefs.current[app.id] = el; }}
                  className={`border-b border-border/60 last:border-0 hover:bg-panel/40 transition-colors group ${
                    focusedAppId === app.id ? "bg-accent-soft" : ""
                  }`}
                >
                  <td className="py-3.5 px-5 text-ink font-medium max-w-[180px] truncate">{app.job_title}</td>
                  <td className="py-3.5 px-5 text-muted">{app.company}</td>
                  <td className="py-3.5 px-5 text-xs text-muted">{app.resume_label}</td>
                  <td className="py-3.5 px-5"><ScoreBadge score={app.match_score} /></td>
                  <td className="py-3.5 px-5 text-xs text-muted whitespace-nowrap">
                    {new Date(app.applied_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </td>
                  <td className="py-3.5 px-5"><StatusPill status={app.status} /></td>
                  <td className="py-3.5 px-5">
                    <div className="flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => setCoverApp(app)}
                        className="text-xs font-medium text-muted hover:text-ink transition-colors"
                      >Letter</button>
                      <select
                        className="text-xs bg-panel text-ink rounded-full px-2.5 py-1 outline-none cursor-pointer hover:bg-border/60 transition-colors"
                        value={app.status}
                        disabled={updatingId === app.id}
                        onChange={e => handleStatus(app, e.target.value)}
                      >
                        {statusOrder.map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                  </td>
                </tr>
              ))}
              {apps.length === 0 && (
                <tr><td colSpan={7} className="py-16 text-center text-muted text-sm">No applications yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {coverApp && <CoverDrawer app={coverApp} onClose={() => setCoverApp(null)} />}
    </div>
  );
}
