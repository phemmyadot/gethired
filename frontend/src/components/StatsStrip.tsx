import { type Stats } from "../lib/api";
import { StatCard } from "./ui";

export function StatsStrip({ stats }: { stats: Stats | null }) {
  return (
    <div className="border-b border-border flex overflow-x-auto shrink-0">
      <StatCard label="Jobs fetched"  value={stats?.total_jobs ?? 0} />
      <StatCard label="Resumes"       value={stats?.total_resumes ?? 0} />
      <StatCard label="Matches ≥70%"  value={stats?.total_matches ?? 0} accent="text-sky" />
      <StatCard label="Applied"       value={stats?.total_applied ?? 0} accent="text-teal" />
      <StatCard label="Interviews"    value={stats?.interviews ?? 0} accent="text-amber" />
      <StatCard label="Offers"        value={stats?.offers ?? 0} accent="text-teal" />
    </div>
  );
}
