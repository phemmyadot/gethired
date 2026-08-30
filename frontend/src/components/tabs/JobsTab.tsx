import { useState } from "react";
import { type Job } from "../../lib/api";
import { SourceTag } from "../ui";

export function JobsTab({ jobs }: { jobs: Job[] }) {
  const [source, setSource] = useState<string>("all");
  const sources = ["all", ...Array.from(new Set(jobs.map(j => j.source)))];
  const filtered = source === "all" ? jobs : jobs.filter(j => j.source === source);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 flex-wrap">
        {sources.map(s => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={`text-xs px-3 py-1.5 rounded border transition-colors capitalize ${
              source === s
                ? "bg-teal/10 border-teal/40 text-teal"
                : "border-border text-muted hover:text-text"
            }`}
          >
            {s}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted">{filtered.length} listings</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              {["Role", "Company", "Location", "Source", "Fetched", ""].map(h => (
                <th key={h} className="text-left text-xs text-muted font-normal pb-2 pr-4 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((j, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-panel/40 transition-colors">
                <td className="py-2.5 pr-4 text-text max-w-[200px] truncate">{j.title}</td>
                <td className="py-2.5 pr-4 text-muted">{j.company}</td>
                <td className="py-2.5 pr-4 text-xs text-muted">{j.remote ? "Remote" : j.location || "—"}</td>
                <td className="py-2.5 pr-4"><SourceTag source={j.source} /></td>
                <td className="py-2.5 pr-4 text-xs text-muted whitespace-nowrap">
                  {new Date(j.fetched_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </td>
                <td className="py-2.5">
                  <a
                    href={j.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-teal hover:underline"
                    onClick={e => e.stopPropagation()}
                  >
                    view
                  </a>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="py-12 text-center text-muted text-sm">No jobs fetched yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
