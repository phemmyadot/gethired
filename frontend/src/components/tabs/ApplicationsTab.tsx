import { useState } from "react";
import { updateAppStatus, type Application } from "../../lib/api";
import { ScoreBadge, StatusPill } from "../ui";
import { CoverDrawer } from "../CoverDrawer";

export function ApplicationsTab({ apps, onRefresh }: { apps: Application[]; onRefresh: () => void }) {
  const [coverApp, setCoverApp] = useState<Application | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const statusOrder = ["applied", "interview", "offer", "rejected", "ghosted", "failed"];

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
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {["Role", "Company", "Resume", "Score", "Applied", "Status", "Actions"].map(h => (
                <th key={h} className="text-left text-xs text-muted font-normal pb-2 pr-4 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {apps.map((app, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-panel/30 transition-colors group">
                <td className="py-2.5 pr-4 text-text font-medium max-w-[180px] truncate">{app.job_title}</td>
                <td className="py-2.5 pr-4 text-muted">{app.company}</td>
                <td className="py-2.5 pr-4 text-xs text-muted">{app.resume_label}</td>
                <td className="py-2.5 pr-4"><ScoreBadge score={app.match_score} /></td>
                <td className="py-2.5 pr-4 text-xs text-muted whitespace-nowrap">
                  {new Date(app.applied_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </td>
                <td className="py-2.5 pr-4"><StatusPill status={app.status} /></td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => setCoverApp(app)}
                      className="text-xs text-muted hover:text-text transition-colors"
                    >letter</button>
                    <select
                      className="text-xs bg-panel border border-border text-muted rounded px-1 py-0.5 outline-none cursor-pointer hover:border-teal/40 transition-colors"
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
              <tr><td colSpan={7} className="py-12 text-center text-muted text-sm">No applications yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {coverApp && <CoverDrawer app={coverApp} onClose={() => setCoverApp(null)} />}
    </div>
  );
}
