"use client";
import Head from "next/head";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  getStats, getMatches, getApplications, getResumes, getJobs, triggerPipeline, getPipelineStatus,
  type Stats, type Match, type Application, type Resume, type Job, type PipelineStatus,
} from "../lib/api";
import { Sidebar, type Tab } from "../components/Sidebar";
import { StatsStrip } from "../components/StatsStrip";
import { DashboardTab } from "../components/tabs/DashboardTab";
import { MatchesTab } from "../components/tabs/MatchesTab";
import { ApplicationsTab } from "../components/tabs/ApplicationsTab";
import { ResumesTab } from "../components/tabs/ResumesTab";
import { JobsTab } from "../components/tabs/JobsTab";

const IN_PROGRESS_STATUSES = ["running", "ingesting", "matching", "applying"];

export default function Home() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [stats, setStats] = useState<Stats | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>(null);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [focusedAppId, setFocusedAppId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function viewApplication(applicationId: string) {
    setFocusedAppId(applicationId);
    setTab("applications");
  }

  const load = useCallback(async () => {
    const s = await getStats().catch(() => null);
    if (s) setStats(s);

    const [m, a, r, j] = await Promise.allSettled([
      getMatches(s?.score_threshold ?? 0.7), getApplications(), getResumes(), getJobs(),
    ]);
    if (m.status === "fulfilled") setMatches(m.value);
    if (a.status === "fulfilled") setApps(a.value);
    if (r.status === "fulfilled") setResumes(r.value);
    if (j.status === "fulfilled") setJobs(j.value);
  }, []);

  useEffect(() => { load(); }, [load]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollStatus = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const status = await getPipelineStatus().catch(() => null);
      setPipelineStatus(status);
      if (!status || !IN_PROGRESS_STATUSES.includes(status.status)) {
        stopPolling();
        setLastRun(new Date().toLocaleTimeString());
        load();
      }
    }, 1500);
  }, [load, stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  async function handlePipeline() {
    setPipelineRunning(true);
    try {
      await triggerPipeline();
      pollStatus();
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
    <div className="flex h-screen overflow-hidden bg-paper">
      <Head>
        <title>JobBot — AI application engine</title>
      </Head>
      <Sidebar
        tab={tab}
        onTabChange={setTab}
        navItems={navItems}
        pipelineRunning={pipelineRunning}
        onRunPipeline={handlePipeline}
        lastRun={lastRun}
        pipelineStatus={pipelineStatus}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        <StatsStrip stats={stats} />

        <div className="flex-1 overflow-y-auto px-8 pb-8">
          {tab === "dashboard"    && <DashboardTab stats={stats} />}
          {tab === "matches"      && <MatchesTab matches={matches} resumes={resumes} onRefresh={load} onViewApplication={viewApplication} />}
          {tab === "applications" && <ApplicationsTab apps={apps} onRefresh={load} focusedAppId={focusedAppId} onFocusHandled={() => setFocusedAppId(null)} />}
          {tab === "resumes"      && <ResumesTab resumes={resumes} onRefresh={load} />}
          {tab === "jobs"         && <JobsTab jobs={jobs} onViewApplication={viewApplication} />}
        </div>
      </main>
    </div>
  );
}
