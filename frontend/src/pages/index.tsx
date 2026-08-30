"use client";
import { useState, useEffect, useCallback } from "react";
import {
  getStats, getMatches, getApplications, getResumes, getJobs, triggerPipeline,
  type Stats, type Match, type Application, type Resume, type Job,
} from "../lib/api";
import { Sidebar, type Tab } from "../components/Sidebar";
import { StatsStrip } from "../components/StatsStrip";
import { DashboardTab } from "../components/tabs/DashboardTab";
import { MatchesTab } from "../components/tabs/MatchesTab";
import { ApplicationsTab } from "../components/tabs/ApplicationsTab";
import { ResumesTab } from "../components/tabs/ResumesTab";
import { JobsTab } from "../components/tabs/JobsTab";

export default function Home() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [stats, setStats] = useState<Stats | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [s, m, a, r, j] = await Promise.allSettled([
      getStats(), getMatches(0), getApplications(), getResumes(), getJobs(),
    ]);
    if (s.status === "fulfilled") setStats(s.value);
    if (m.status === "fulfilled") setMatches(m.value);
    if (a.status === "fulfilled") setApps(a.value);
    if (r.status === "fulfilled") setResumes(r.value);
    if (j.status === "fulfilled") setJobs(j.value);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handlePipeline() {
    setPipelineRunning(true);
    try {
      await triggerPipeline();
      setLastRun(new Date().toLocaleTimeString());
      setTimeout(load, 3000);
    } finally {
      setPipelineRunning(false);
    }
  }

  const pendingMatches = matches.filter(m => !m.applied).length;

  const navItems: { id: Tab; icon: string; label: string; badge?: number }[] = [
    { id: "dashboard",    icon: "◈",  label: "Overview" },
    { id: "matches",      icon: "⟐",  label: "Matches",      badge: pendingMatches },
    { id: "applications", icon: "✉",  label: "Applications", badge: apps.filter(a => a.status === "interview").length },
    { id: "resumes",      icon: "📄", label: "Resumes",      badge: resumes.length },
    { id: "jobs",         icon: "⊞",  label: "Jobs feed" },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-ink">
      <Sidebar
        tab={tab}
        onTabChange={setTab}
        navItems={navItems}
        pipelineRunning={pipelineRunning}
        onRunPipeline={handlePipeline}
        lastRun={lastRun}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        <StatsStrip stats={stats} />

        <div className="flex-1 overflow-y-auto p-6">
          {tab === "dashboard"    && <DashboardTab stats={stats} />}
          {tab === "matches"      && <MatchesTab matches={matches} onRefresh={load} />}
          {tab === "applications" && <ApplicationsTab apps={apps} onRefresh={load} />}
          {tab === "resumes"      && <ResumesTab resumes={resumes} onRefresh={load} />}
          {tab === "jobs"         && <JobsTab jobs={jobs} />}
        </div>
      </main>
    </div>
  );
}
