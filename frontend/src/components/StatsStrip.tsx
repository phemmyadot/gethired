import { type Stats } from "../lib/api";
import { StatCard } from "./ui";

export function StatsStrip({ stats }: { stats: Stats | null }) {
  return (
    <div className="flex gap-4 overflow-x-auto shrink-0 px-8 py-6">
      <StatCard label="Jobs fetched"  value={stats?.total_jobs ?? 0} />
      <StatCard label="Resumes"       value={stats?.total_resumes ?? 0} />
      <StatCard label={`Matches ≥${Math.round((stats?.score_threshold ?? 0.7) * 100)}%`}  value={stats?.total_matches ?? 0} accent="text-sky" />
      <StatCard label="Applied"       value={stats?.total_applied ?? 0} accent="text-teal" />
      <StatCard label="Interviews"    value={stats?.interviews ?? 0} accent="text-amber" />
      <StatCard label="Offers"        value={stats?.offers ?? 0} accent="text-teal" />
    </div>
  );
}
